"""Prepare source-only Docker contexts from committed allowlists, never dirty files."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile


BASE_DIGESTS = {
    'api': 'sha256:0e732660b3438f78212e567ccc6b65f09764ed578678f2ba887d22d0d08fac5a',
    'ai': 'sha256:475a6ae2a2d6e2f5060c31e3d0a88ea5a2474d951cc0e74c84f951bf3fb92918',
}
API_FILES = (
    'lms_api/lms/api.py', 'lms_api/lms/chatbot_warmup.py',
    'lms_api/lms/cohort_documents.py', 'lms_api/lms/content_commands.py',
    'lms_api/lms/curriculum_validation.py', 'lms_api/lms/commands.py',
    'lms_api/lms/jwt_auth.py', 'lms_api/lms/middleware.py', 'lms_api/lms/auth_sessions.py',
    'lms_api/lms/test_auth_security.py', 'lms_api/lms/test_password_http.py',
    'lms_api/lms/test_curriculum_validation.py', 'lms_api/lms/test_regulation_upload.py',
    'chatbot/cohort_document_rag.py', 'chatbot/database.py', 'chatbot/active_policy_rules.py',
    'chatbot/document_calculation_rules.py', 'chatbot/calculation_rules.py',
    'chatbot/calculation_rules.json', 'chatbot/unit_period.py',
    'chatbot/tests/__init__.py', 'chatbot/tests/test_regulation_ingestion.py',
    'chatbot/tests/test_calendar_basis.py',
)
VECTOR_FILES = ('vectordb/policy_ingestion.py', 'vectordb/utills.py')


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def prepare(repo: Path, commit: str, base_commit: str, output: Path) -> Path:
    repo, output = repo.resolve(), output.resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Choose a new output directory: {output}')
    revision = git(repo, 'rev-parse', '--verify', f'{commit}^{{commit}}').decode().strip()
    baseline = git(repo, 'rev-parse', '--verify', f'{base_commit}^{{commit}}').decode().strip()
    # Immutable base dependencies can only be retained if requirement files
    # are unchanged relative to the develop integration baseline.
    git(repo, 'diff', '--exit-code', baseline, revision, '--',
        'requirements.txt', 'lms_api/requirements.txt')
    tracked = git(repo, 'ls-tree', '-r', '--name-only', revision, '--', 'chatbot').decode().splitlines()
    ai_files = tuple(path for path in tracked if (
        path.endswith('.py') and (not path.startswith('chatbot/evaluation/')
            or path in ('chatbot/evaluation/__init__.py', 'chatbot/evaluation/policy_hybrid.py'))
    ) or path == 'chatbot/calculation_rules.json') + VECTOR_FILES
    manifests, prepared = {}, {}
    for kind, paths in (('api', API_FILES + VECTOR_FILES), ('ai', ai_files)):
        files, manifest_rows = {}, []
        for path in paths:
            data = git(repo, 'show', f'{revision}:{path}')
            destination = 'app/' + (path[len('lms_api/'):] if path.startswith('lms_api/') else path)
            files[destination] = data
            manifest_rows.append({'source': path, 'destination': destination,
                'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'mode': '0644'})
        files['Dockerfile'] = git(repo, 'show', f'{revision}:deploy/login-warmup-{kind}.overlay.Dockerfile')
        manifest = {'source_commit': revision, 'develop_baseline': baseline, 'kind': kind,
                    'required_base_digest': BASE_DIGESTS[kind], 'requirements_changed': False,
                    'parent_user_cmd_env_preserved': True, 'files': manifest_rows}
        files['manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
        manifests[kind], prepared[kind] = manifest, files
    output.mkdir(parents=True, exist_ok=False)
    for kind, files in prepared.items():
        root = output / kind
        root.mkdir()
        with tarfile.open(output / f'{kind}-context.tar.gz', 'w:gz') as archive:
            for relative, data in sorted(files.items()):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as stream:
                    stream.write(data)
                target.chmod(0o644)
                info = tarfile.TarInfo(relative)
                info.size, info.mode, info.mtime = len(data), 0o644, 0
                archive.addfile(info, io.BytesIO(data))
    release = output / 'release-manifest.json'
    with release.open('x', encoding='utf-8') as stream:
        json.dump(manifests, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return release


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--base-commit', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.repo, args.commit, args.base_commit, args.output_dir))
