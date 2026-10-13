"""API planning packaging without an AI server, DB connection or network."""
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless

ROOT = Path(__file__).resolve().parents[2]


@skipUnless((ROOT / 'lms_api/Dockerfile').is_file(), 'source-level Docker packaging check')
class ApiPlanningPackageTests(TestCase):
    def test_api_dockerfile_copies_planning_into_searchable_app_package(self):
        dockerfile = (ROOT / 'lms_api/Dockerfile').read_text(encoding='utf-8')
        self.assertIn('ENV PYTHONPATH=/app/cover_letter_rag:/app', dockerfile)
        self.assertIn('cover_letter_rag/app/job_requirements.py /app/cover_letter_rag/app/', dockerfile)
        self.assertIn('COPY cover_letter_rag/app/application_planning/ /app/cover_letter_rag/app/application_planning/', dockerfile)
        self.assertNotIn('COPY cover_letter_rag /app/cover_letter_rag', dockerfile)

    def test_minimal_flat_api_package_imports_without_repository_path(self):
        with TemporaryDirectory() as directory:
            package = Path(directory) / 'cover_letter_rag/app'
            package.mkdir(parents=True)
            for name in ('__init__.py', 'models.py', 'job_requirements.py'):
                shutil.copyfile(ROOT / 'cover_letter_rag/app' / name, package / name)
            shutil.copytree(ROOT / 'cover_letter_rag/app/application_planning', package / 'application_planning',
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            code = '\n'.join([
                'import sys,socket,importlib.abc;sys.path.insert(0,sys.argv[1])',
                'class NoAI(importlib.abc.MetaPathFinder):',
                ' def find_spec(self,fullname,path=None,target=None):',
                '  if fullname.split(".")[0] in {"langchain_core","langchain_openai","langgraph","openai","firebase_admin"}: raise ImportError("AI libraries unavailable")',
                'sys.meta_path.insert(0,NoAI())',
                'socket.create_connection=lambda *a,**k: (_ for _ in ()).throw(AssertionError("No network"))',
                'from app.application_planning.engine import parse_constraints,validate_analysis,validate_plan',
                'from app.application_planning.models import Question,Constraints,PlanningInput,PlanningResult',
                'from app.job_requirements import JobRequirement,requirement_cache_key,REQUIREMENT_PROMPT_VERSION',
                'assert requirement_cache_key({"job_id":"synthetic","snapshot_hash":"a"*64}).endswith(REQUIREMENT_PROMPT_VERSION)',
                'assert callable(parse_constraints) and callable(validate_analysis) and callable(validate_plan)',
                'assert "app.main" not in sys.modules and "langchain_openai" not in sys.modules',
                'print("minimal API planning import OK")',
            ])
            result = subprocess.run([sys.executable, '-I', '-c', code, str(package.parent)], cwd=directory,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('minimal API planning import OK', result.stdout)
