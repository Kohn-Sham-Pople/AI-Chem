from ..config import loads
from ..provenance import digest


def derive_calculation_key(bundle):
    m=loads(bundle.manifest_json); c=loads(bundle.resolved_json)
    return digest('submission-calculation-v1',dict(science=m['science_identity'],
        structure=m['resolved_refs']['structure_id'],structure_sha256=m['generated_files']['POSCAR']['sha256'],
        kpoints=m['generated_files']['KPOINTS']['sha256'],potcar=m['generated_files']['POTCAR']['sha256'],
        template=m['resolved_refs']['template'],protocol=m['resolved_refs']['protocol'],stage=m['identity']['stage_id'],
        vasp=c['profile']['vasp']['version'],generator=m['generator_version'],hash_version=m['hash_schema_version']))


def derive_bundle_key(bundle,profile):
    return digest('submission-location-v1',dict(cluster=profile['cluster_id'],epoch=profile['cluster_epoch'],path=bundle.path))


def request_digest(bundle,profile,calculation_key,bundle_key):
    return digest('submission-request-v1',dict(bundle=bundle_key,manifest=bundle.manifest_sha256,
        calculation=calculation_key,profile=profile))
