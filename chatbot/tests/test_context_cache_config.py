"""Dedicated Redis configuration and opt-in deployment, without connections."""
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import yaml

from chatbot import context_cache as cache
from chatbot.firebase_student_context import _redis as general_redis


class ContextCacheConfigTests(TestCase):
    def setUp(self):
        cache.redis_client.cache_clear()
        self.addCleanup(cache.redis_client.cache_clear)

    def assert_url(self, env, expected):
        cache.redis_client.cache_clear()
        with patch.dict(os.environ, env, clear=True), patch('redis.Redis.from_url') as factory:
            cache.redis_client()
        self.assertEqual(factory.call_args.args[0], expected)
        self.assertEqual(factory.call_args.kwargs['socket_timeout'], cache.REDIS_TIMEOUT_SECONDS)
        self.assertEqual(factory.call_args.kwargs['socket_connect_timeout'], cache.REDIS_TIMEOUT_SECONDS)

    def test_dedicated_url_wins_over_general_url(self):
        self.assert_url({'CHATBOT_CONTEXT_REDIS_URL': ' redis://chat-cache:6379/0 ',
                         'REDIS_URL': 'redis://auth-cache:6379/1'}, 'redis://chat-cache:6379/0')

    def test_unset_empty_or_whitespace_dedicated_url_falls_back(self):
        for dedicated in (None, '', '   '):
            with self.subTest(dedicated=dedicated):
                env = {'REDIS_URL': 'redis://general-cache:6379/2'}
                if dedicated is not None:
                    env['CHATBOT_CONTEXT_REDIS_URL'] = dedicated
                self.assert_url(env, 'redis://general-cache:6379/2')

    def test_unset_empty_or_whitespace_both_urls_use_local_default(self):
        for env in ({}, {'CHATBOT_CONTEXT_REDIS_URL': '', 'REDIS_URL': ''},
                    {'CHATBOT_CONTEXT_REDIS_URL': ' ', 'REDIS_URL': ' '}):
            with self.subTest(env=env):
                self.assert_url(env, 'redis://127.0.0.1:6379/0')

    def test_general_redis_consumer_is_unchanged(self):
        env = {'CHATBOT_CONTEXT_REDIS_URL': 'redis://chat-cache:6379/0',
               'REDIS_URL': 'redis://general-cache:6379/2'}
        with patch.dict(os.environ, env, clear=True), patch('redis.Redis.from_url') as factory:
            cache.redis_client()
            general_redis()
        self.assertEqual(factory.call_args_list[0].args[0], env['CHATBOT_CONTEXT_REDIS_URL'])
        self.assertEqual(factory.call_args_list[1].args[0], env['REDIS_URL'])

    def test_overlay_is_opt_in_private_and_does_not_gate_ai_startup(self):
        root = Path(__file__).resolve().parents[2]
        base = yaml.safe_load((root / 'deploy/docker-compose.ai.yml').read_text(encoding='utf-8'))
        overlay = yaml.safe_load((root / 'deploy/docker-compose.chat-cache.yml').read_text(encoding='utf-8'))
        self.assertNotIn('chat-cache', base['services'])
        ai, redis = overlay['services']['ai'], overlay['services']['chat-cache']
        self.assertEqual(ai['environment']['CHATBOT_CONTEXT_REDIS_URL'], 'redis://chat-cache:6379/0')
        self.assertEqual(ai['environment']['LMS_CHATBOT_WARMUP'], '${LMS_CHATBOT_WARMUP:-0}')
        self.assertNotIn('REDIS_URL', ai['environment'])
        self.assertNotIn('depends_on', ai)
        self.assertNotIn('ports', redis)
        self.assertNotIn('volumes', redis)
        self.assertEqual(redis['image'], 'redis:7')
        self.assertEqual(redis['mem_limit'], '256m')
        self.assertEqual(redis['networks'], ['default'])
        command = redis['command']
        for key, value in (('--maxmemory', '128mb'), ('--maxmemory-policy', 'noeviction'),
                           ('--appendonly', 'no'), ('--save', '')):
            self.assertEqual(command[command.index(key) + 1], value)
        self.assertEqual(redis['healthcheck']['test'], ['CMD', 'redis-cli', 'ping'])
