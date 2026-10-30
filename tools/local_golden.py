"""Run only on approved HPC storage. No actual research fixtures belong in Git.

The expectation must be authored/reviewed independently before this command.
It contains exact source/generated hashes and semantic changes, not guesses.
"""
import argparse
from pathlib import Path
from ai_chem_input.config import checked,load
from ai_chem_input.worker import operator
from ai_chem_input.prepare import build_plan,materialize,verify_bundle
from ai_chem_input.provenance import canonical,sha256
from ai_chem_input.paths import inspect,private_dir,write_new
from ai_chem_input.errors import require


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--config',required=True); p.add_argument('--request',required=True)
    p.add_argument('--expected',required=True)
    args=p.parse_args(); _,reg,profile=operator(args.config)
    request=checked(load(args.request),'request'); expected=load(args.expected)
    require(set(expected)=={'reviewer','approved_at','source_sha256','generated_sha256','semantic_changes'},'GOLDEN_EXPECTATION')
    require(expected['reviewer'] and expected['approved_at'],'GOLDEN_EXPECTATION')
    plan=build_plan((request,reg)); from ai_chem_input.config import loads
    require({s.name:s.sha256 for s in plan.sources}==expected['source_sha256'],'GOLDEN_SOURCE')
    hashes={k:sha256(v) for k,v in plan.generated}; hashes['POTCAR']=next(s.sha256 for s in plan.sources if s.name=='POTCAR')
    require(hashes==expected['generated_sha256'],'GOLDEN_INPUT')
    require(loads(plan.semantic_json)==expected['semantic_changes'],'GOLDEN_DIFF')
    result=materialize(plan); verified=verify_bundle(Path(plan.final_dir))
    for s in plan.sources: inspect(s.path,s.expected)
    evidence=dict(schema_version=1,reviewer=expected['reviewer'],approved_at=expected['approved_at'],
                  source_sha256=expected['source_sha256'],generated_sha256=hashes,
                  species_blocks=loads(plan.config_json)['material']['species_blocks'],
                  configurations=loads(plan.config_json)['material']['configurations'],
                  u_sets=loads(plan.config_json)['material']['u_sets'],
                  manifest_sha256=verified['manifest_sha256'],result=result['result'])
    dest=private_dir(Path(profile['roots']['state'])/'golden')/(request['calculation_id']+'_'+request['stage_id']+'.json')
    write_new(dest,canonical(evidence))
    print('LOCAL_GOLDEN_PASSED (private evidence retained locally)')

if __name__=='__main__': main()
