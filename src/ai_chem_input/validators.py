import re

from .errors import require
from .incar import array, boolean, number, parse_incar, Patch
from .protocols import CONTROLLED, MATERIAL_TAGS, stage_values
from .provenance import sha256

MAGMOM_MAX_LINE_BYTES = 255


def compress_magmom(moments):
    """Run-length encode adjacent equal scalar components, without float rounding."""
    require(moments,'MAGMOM_COUNT')
    expected=tuple(number(value) for value in moments)
    tokens=[]; start=0
    while start<len(expected):
        end=start+1
        while end<len(expected) and expected[end]==expected[start]:
            end+=1
        count=end-start
        tokens.append(str(count)+'*'+moments[start] if count>1 else moments[start])
        start=end
    value=' '.join(tokens)
    require(array(value)==expected,'MAGMOM_MAPPING')
    require(len(('MAGMOM = '+value).encode('utf-8'))<=MAGMOM_MAX_LINE_BYTES,
            'MAGMOM_LINE_TOO_LONG','MAGMOM')
    return value


def validate_magmom_line_lengths(doc):
    """Bound the logical assignment and every actual physical line it touches."""
    assignment=next((a for a in doc.assignments if a.tag=='MAGMOM'),None)
    if assignment is None:
        return  # The existing mapping validation reports a missing MAGMOM.
    text=doc.data.decode('utf-8')
    start=max(text.rfind('\n',0,assignment.start),text.rfind('\r',0,assignment.start))+1
    endings=[text.find(separator,assignment.end) for separator in ('\r','\n')]
    end=min([pos for pos in endings if pos>=0]+[len(text)])
    lines=re.split(r'\r\n|\r|\n',text[start:end])
    logical='MAGMOM = '+' '.join(doc.tags['MAGMOM'].split())
    require(all(len(line.encode('utf-8'))<=MAGMOM_MAX_LINE_BYTES for line in lines)
            and len(logical.encode('utf-8'))<=MAGMOM_MAX_LINE_BYTES,
            'MAGMOM_LINE_TOO_LONG','MAGMOM')


def one(items,key,value,code):
    matches=[v for v in items if v[key]==value]
    require(len(matches)==1,code)
    require(len({v[key] for v in items})==len(items),code)
    return matches[0]


def material_mapping(material,request,structure,potentials):
    blocks=material['species_blocks']; ids=[b['block_id'] for b in blocks]
    require(len(ids)==len(set(ids)) and len(blocks)==len(structure.counts)==len(potentials),'SPECIES_MISMATCH')
    for i,(block,potential) in enumerate(zip(blocks,potentials)):
        require(block['element']==structure.species[i] and block['count']==structure.counts[i] and potential.element==block['element'],'SPECIES_MISMATCH')
        require(block['potential_variant']==potential.variant and block['dataset_sha256']==potential.sha256,'POTENTIAL_MISMATCH')
    config=one(material['configurations'],'configuration_id',request['configuration_id'],'CONFIGURATION_INVALID')
    registered_structure=one(material['structures'],'structure_id',request['structure_id'],'STRUCTURE_INVALID')
    require(config['structure_id']==request['structure_id'] and config['structure_sha256']==registered_structure['sha256'],'STRUCTURE_INVALID')
    uset=one(material['u_sets'],'u_set_id',request['u_set_id'],'LDAU_MAPPING_INVALID')
    require(uset['u_set_id'] in material['method']['approved_u_set_ids'],'UNSUPPORTED_METHOD')
    require(uset['ldau'] and uset['ldautype'] in (1,2) and set(uset['by_block'])==set(ids),'LDAU_MAPPING_INVALID')
    for block in blocks:
        value=uset['by_block'][block['block_id']]
        if block['element']=='Eu': require(value['l']==3,'LDAU_MAPPING_INVALID')
        if block['element']=='Cu': require(value['l']==2,'LDAU_MAPPING_INVALID')
        number(value['u_eV']); number(value['j_eV'])
    patches=[Patch('LDAU','.TRUE.'),Patch('LDAUTYPE',str(uset['ldautype']))]
    for tag,key in [('LDAUL','l'),('LDAUU','u_eV'),('LDAUJ','j_eV')]:
        patches.append(Patch(tag,' '.join(str(uset['by_block'][b][key]) for b in ids)))
    n=structure.nions; atoms=config['magmom_by_atom']
    require(len(atoms)==n and sorted(a['atom_index'] for a in atoms)==list(range(1,n+1)),'MAGMOM_COUNT')
    moments=[]
    for atom in sorted(atoms,key=lambda a:a['atom_index']):
        if config['spin_mode']=='collinear':
            require(set(atom)=={'atom_index','moment'},'MAGMOM_COUNT'); moments.append(atom['moment'])
        else:
            require(set(atom)=={'atom_index','vector'} and len(atom['vector'])==3,'MAGMOM_COUNT'); moments.extend(atom['vector'])
    patches.append(Patch('MAGMOM',compress_magmom(moments)))
    return config,uset,patches


def semantic_equal(tag,left,right):
    from .incar import NUMERIC, BOOL
    if tag in NUMERIC: return array(left)==array(right)
    if tag in BOOL: return boolean(left)==boolean(right)
    return left==right


def check_method(material,source_tags):
    require('NSW' not in source_tags or array(source_tags['NSW'])==(0,),'UNSUPPORTED_CALCULATION')
    require('IBRION' not in source_tags or array(source_tags['IBRION'])==(-1,),'UNSUPPORTED_CALCULATION')
    require(not set(source_tags)&set('NELECT NUPDOWN I_CONSTRAINED_M M_CONSTR LAMBDA METAGGA'.split()),'UNSUPPORTED_METHOD')
    require(not boolean(source_tags.get('LHFCALC','F')),'UNSUPPORTED_METHOD')
    actual={k:v for k,v in source_tags.items() if k not in CONTROLLED|MATERIAL_TAGS}
    expected=material['method']['incar_tags']
    require(set(actual)==set(expected),'METHOD_MISMATCH')
    for k,v in expected.items(): require(semantic_equal(k,actual[k],v),'METHOD_MISMATCH',k)


def check_spin(config,tags):
    soc=boolean(tags.get('LSORBIT','F')); ncl=boolean(tags.get('LNONCOLLINEAR','F'))
    require(soc==config['soc'],'SPIN_MODE_CONFLICT')
    require(not (soc and 'LNONCOLLINEAR' in tags and not ncl),'SPIN_MODE_CONFLICT')
    require((soc or ncl)==(config['spin_mode']=='noncollinear'),'SPIN_MODE_CONFLICT')
    if config['spin_mode']=='collinear':
        require(array(tags.get('ISPIN','1'))==(2,) and not soc and config['saxis'] is None,'SPIN_MODE_CONFLICT')
    if soc or config['saxis'] is not None:
        require(config['saxis'] is not None and len(config['saxis'])==3,'SPIN_MODE_CONFLICT')
        expected=tuple(number(v) for v in config['saxis'])
        require(any(v!=0 for v in expected) and array(tags.get('SAXIS','0 0 0'))==expected,'SPIN_MODE_CONFLICT')


def validate_inputs(context,inputs):
    """Raise on errors; successful explicit validation has no issues."""
    from .poscar import parse_poscar
    from .kpoints import validate_kpoints
    material=context['material']; request=context['request']; potentials=context['potentials']
    structure=parse_poscar(inputs['POSCAR'],[b['element'] for b in material['species_blocks']])
    config,uset,patches=material_mapping(material,request,structure,potentials)
    require(sha256(inputs['POSCAR'])==config['structure_sha256'],'STRUCTURE_INVALID')
    require(sha256(inputs['KPOINTS'])==material['method']['kpoints_sha256'],'KPOINTS_MISMATCH'); validate_kpoints(inputs['KPOINTS'])
    doc=parse_incar(inputs['INCAR']); validate_magmom_line_lengths(doc)
    tags=doc.tags; check_method(material,tags); check_spin(config,tags)
    for patch in patches:
        require(patch.tag in tags,'MAGMOM_COUNT' if patch.tag=='MAGMOM' else 'LDAU_MAPPING_INVALID')
        actual=array(tags[patch.tag]) if patch.tag!='LDAU' else boolean(tags[patch.tag])
        expected=array(patch.value) if patch.tag!='LDAU' else boolean(patch.value)
        if patch.tag=='MAGMOM':
            require(len(actual)==len(expected),'MAGMOM_COUNT'); require(actual==expected,'MAGMOM_MAPPING')
        else: require(actual==expected,'LDAU_MAPPING_INVALID')
    for tag,value in stage_values(context['template']['shell_class'],request['stage_id']).items():
        if value is None: require(tag not in tags,'PROTOCOL_MISMATCH',tag)
        else: require(tag in tags and semantic_equal(tag,tags[tag],value),'PROTOCOL_MISMATCH',tag)
    return []


def semantic_tag_value(tag,raw):
    """Exact decimal representation without float conversion/context rounding."""
    from .incar import NUMERIC,BOOL
    if tag in BOOL: return boolean(raw)
    if tag not in NUMERIC: return raw
    out=[]
    for value in array(raw):
        sign,digits,exponent=value.as_tuple(); digits=list(digits)
        if value==0: out.append('0'); continue
        while len(digits)>1 and digits[-1]==0:
            digits.pop(); exponent+=1
        out.append(('-' if sign else '')+''.join(str(d) for d in digits)+'e'+str(exponent))
    return out
