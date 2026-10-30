"""Synthetic-only registry builder. Never used by the production package."""
import shutil
from pathlib import Path
from ai_chem_input.registry import Registry
from ai_chem_input.provenance import canonical,sha256
from ai_chem_input.paths import inspect
from ai_chem_input.potcar import inspect_potcar
from ai_chem_input.discovery import inventory


def setup(root,shell='f'):
    root=Path(root); root.mkdir(mode=0o700,parents=True,exist_ok=True)
    source=root/'research'; source.mkdir(mode=0o700)
    shutil.copytree(Path(__file__).parent/'fixtures/synthetic'/shell,source/shell)
    src=source/shell
    bins=root/'bin'; bins.mkdir(); lib=root/'lib'; lib.mkdir(); (lib/'fake.so').write_bytes(b'SYNTHETIC TEST ONLY')
    for name in ('vasp_ncl','mpi','python'):
        file=bins/name; file.write_bytes(b'SYNTHETIC TEST ONLY -- NEVER EXECUTE'); file.chmod(0o700)
    approval=dict(reviewer='synthetic',approved_at='2026-10-30T00:00:00Z',note='SYNTHETIC TEST ONLY')
    def entity(name,**kw): return dict(schema_version=1,id=name,revision=1,approval=approval,**kw)
    roots={k:str(root/k) for k in ('output','registry','state','lock')}; roots.update(source=[str(source)],protected=[str(source)])
    profile=entity('cluster',roots=roots,queue='all.q',pe='mpi_32',slots=32,user_quota_slots=320,
      vasp=dict(version='5.4.4',path=str(bins/'vasp_ncl'),binary_name='vasp_ncl'),
      launcher=dict(path=str(bins/'mpi'),args=['-np',{'token':'NSLOTS'},{'token':'EXECUTABLE'}]),
      environment=dict(fragments=[],library_dirs=[str(lib)],thread_vars=dict(OMP_NUM_THREADS=1,MKL_NUM_THREADS=1)),
      runtime=dict(python_path=str(bins/'python'),bash_path='/bin/bash',walltime=None),
      preparation=dict(max_requests=1,budget_seconds=45,copy_chunk_bytes=128,max_source_bytes=1024*1024,min_free_bytes=1),
      discovery=dict(max_depth=3,max_candidates=100,recursive=False))
    # /bin is a symlink on some cloud hosts; target CentOS /bin is a directory.
    profile['runtime']['bash_path']='/bin/bash'
    with (src/'POTCAR').open('rb') as f: potentials=inspect_potcar(f)
    blocks=[dict(block_id='b'+str(i),element=p.element,count=1,potential_variant=p.variant,dataset_sha256=p.sha256) for i,p in enumerate(potentials)]
    material=entity('material',formula='Eu2BaCuO5' if shell=='f' else 'CaCu(SeO3)2',species_blocks=blocks,
      structures=[dict(structure_id='cell',sha256=inspect(src/'POSCAR')['sha256'])],
      configurations=[dict(configuration_id='FM',structure_id='cell',structure_sha256=inspect(src/'POSCAR')['sha256'],spin_mode='collinear',soc=False,saxis=None,
                           magmom_by_atom=[dict(atom_index=1,moment='1'),dict(atom_index=2,moment='-1')])],
      u_sets=[dict(u_set_id='u',ldau=True,ldautype=2,by_block={b['block_id']:dict(l=3 if b['element']=='Eu' else 2 if b['element']=='Cu' else -1,u_eV=str(i+1),j_eV='0') for i,b in enumerate(blocks)})],
      method=dict(incar_tags=dict(SYSTEM='synthetic',ISPIN='2',ENCUT='400',NSW='0',IBRION='-1'),kpoints_sha256=inspect(src/'KPOINTS')['sha256'],potcar_sha256=inspect(src/'POTCAR')['sha256'],approved_u_set_ids=['u']))
    protocol=entity('protocol',shell_class=shell,recipe='open_'+shell+'_v1')
    template=entity('template',material_id='material',shell_class=shell,source_dir=str(src),files=inventory(src)['files'],profile=dict(id='cluster',revision=1),protocol=dict(id='protocol',revision=1))
    r=Registry(root/'registry'); entities=dict(profile=profile,material=material,template=template,protocol=protocol)
    for kind,value in entities.items(): r.register(kind,value,sha256(canonical(value)))
    request=dict(schema_version=1,request_id='req',calculation_id='calc',template=dict(id='template',revision=1),material=dict(id='material',revision=1),cluster_profile=dict(id='cluster',revision=1),protocol=dict(id='protocol',revision=1),structure_id='cell',configuration_id='FM',u_set_id='u',stage_id='s01_e4' if shell=='f' else 's01_e6',restart_evidence_id=None)
    return request,r,entities


def tree(root):
    return {str(p.relative_to(root)):(p.read_bytes(),p.stat().st_mode,p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
