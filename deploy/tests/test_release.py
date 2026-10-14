import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release import Release, wait_command, RemoteOutcomeUnknown
from remote_release import validate, set_image, REGISTRY

class DeploymentTests(unittest.TestCase):
    def test_only_project_digest_images_are_accepted(self):
        release='a'*40+'-123-1'
        validate('api',REGISTRY+'/lms-api@sha256:'+'b'*64,release)
        for value in [REGISTRY+'/lms-api:latest','attacker.test/lms-api@sha256:'+'b'*64,REGISTRY+'/lms-ai@sha256:'+'b'*64]:
            with self.assertRaises(ValueError):validate('api',value,release)
        with self.assertRaises(ValueError):validate('api',REGISTRY+'/lms-api@sha256:'+'b'*64,'../escape')

    def test_env_edit_preserves_secrets_and_other_image(self):
        source="SECRET='literal # value'\nECR_AI_IMAGE=old\nECR_IMAGE=api-old\n"
        result=set_image(source,'ECR_AI_IMAGE','new')
        self.assertIn("SECRET='literal # value'",result)
        self.assertIn('ECR_IMAGE=api-old',result)
        self.assertNotIn('ECR_AI_IMAGE=old',result)
        self.assertEqual(result.count('ECR_AI_IMAGE='),1)

    def release(self):
        obj=Release(MagicMock(),SimpleNamespace(release='test',api_image='api',ai_image='ai',web='web'))
        obj.remote=MagicMock();obj.upload_web=MagicMock();obj.smoke=MagicMock();obj.record=MagicMock()
        return obj

    def test_apply_ai_before_api_and_web(self):
        obj=self.release();calls=[]
        obj.remote.side_effect=lambda *args:calls.append(args)
        obj.upload_web.side_effect=lambda:calls.append(('web',))
        obj.execute()
        self.assertEqual(calls,[('ai','prepare'),('api','prepare'),('api','drain'),('ai','apply'),('api','apply'),('web',)])

    def test_api_failure_restores_both_and_skips_web(self):
        obj=self.release()
        def operation(s,p):
            if (s,p)==('api','apply'):raise RuntimeError('health failure')
        obj.remote.side_effect=operation
        with self.assertRaises(RuntimeError):obj.execute()
        obj.remote.assert_any_call('ai','rollback');obj.remote.assert_any_call('api','rollback')
        obj.upload_web.assert_not_called()
        obj.record.assert_called_once_with('failed',[])

    def test_one_failed_rollback_does_not_skip_other(self):
        obj=self.release()
        def operation(s,p):
            if (s,p) in [('api','apply'),('ai','rollback')]:raise RuntimeError('failure')
        obj.remote.side_effect=operation
        with self.assertRaises(RuntimeError):obj.execute()
        obj.remote.assert_any_call('api','rollback')
        self.assertTrue(obj.record.call_args.args[1])

    def test_web_smoke_failure_restores_prior_index_and_invalidates(self):
        obj=self.release();obj.previous={'index.html':{'Body':b'old','ContentType':'text/html','CacheControl':'no-cache'}}
        obj.modified=['index.html'];obj.smoke.side_effect=RuntimeError('bad index')
        obj.invalidate=MagicMock()
        with self.assertRaises(RuntimeError):obj.execute()
        self.assertEqual(obj.s3.put_object.call_args.kwargs['Body'],b'old')
        obj.invalidate.assert_called_once()

    def test_unknown_remote_outcome_does_not_race_rollback(self):
        obj=self.release();obj.remote.side_effect=RemoteOutcomeUnknown('pending')
        with self.assertRaises(RemoteOutcomeUnknown):obj.execute()
        self.assertEqual(obj.remote.call_count,1)
        self.assertEqual(obj.record.call_args.args[0],'requires-manual-recovery')

    def test_ssm_failure_is_not_success(self):
        ssm=MagicMock();ssm.get_command_invocation.return_value={'Status':'Failed'}
        with self.assertRaises(RuntimeError):wait_command(ssm,'cmd','instance',lambda _:None)

    def test_ssm_waits_for_completion(self):
        ssm=MagicMock();ssm.get_command_invocation.side_effect=[{'Status':'InProgress'},{'Status':'Success'}]
        wait_command(ssm,'cmd','instance',lambda _:None)
        self.assertEqual(ssm.get_command_invocation.call_count,2)

if __name__=='__main__':unittest.main()
