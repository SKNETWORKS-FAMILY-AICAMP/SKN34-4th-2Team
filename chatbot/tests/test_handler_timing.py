import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from chatbot import api


class HandlerTimingTests(TestCase):
    def run_case(self, route, mode='success', broken_snapshot=False):
        clock = [100.0]
        inputs = {'thread_id': 'test', 'student_uid': 'test', 'cohort': 'cohort-test003'}
        session = {'uid': 'test', 'cohort': 'cohort-test003'}

        def delayed(seconds, result):
            def call(*args, **kwargs):
                clock[0] += seconds
                return result
            return call

        class Bot:
            def stream(self, received):
                self.received = dict(received)
                clock[0] += 4
                if mode == 'error':
                    raise ValueError('synthetic')
                if mode != 'empty':
                    yield 'answer'
                clock[0] += 5

            def ops_snapshot(self, received):
                clock[0] += 20
                if broken_snapshot:
                    raise ValueError('snapshot unavailable')
                return {}

        bot = Bot()
        def consume(response):
            return [json.loads(chunk) for chunk in response.body_iterator]

        with ExitStack() as stack:
            stack.enter_context(patch.object(api, 'StreamingResponse', lambda body, **kwargs: SimpleNamespace(body_iterator=body)))
            for name, replacement in {
                'valid_proxy_token': lambda *_: True,
                '_session_from_uid': delayed(1, session),
                '_chat_inputs': delayed(2, inputs),
                '_ready_chatbot': delayed(3, bot),
                '_log_generation_failure': lambda *_: None,
            }.items():
                stack.enter_context(patch.object(api, name, replacement))
            stack.enter_context(patch.object(api.time, 'perf_counter', lambda: clock[0]))
            log = stack.enter_context(patch.object(api, 'write_generation_log', side_effect=delayed(30, 'log')))
            request = api.ProxyChatRequest(uid='test', message='question')
            if route == 'proxy':
                result = api.proxy_chat(request, 'token')
            elif route == 'proxy_stream':
                result = consume(api.proxy_chat_stream(request, 'token'))
            elif route == 'stream':
                result = consume(api.stream_chat(api.ChatRequest(thread_id='test', question='question'), session))
            else:
                result = [json.loads(line) for line in api._ndjson_chat(bot, inputs, session)]
            payload = log.call_args.args[1]
        self.assertFalse(any(key.startswith('handler') for key in bot.received))
        return payload, result

    def test_three_handlers_measure_preparation_and_preserve_generation_clock(self):
        for route in ('proxy', 'proxy_stream', 'stream'):
            with self.subTest(route=route):
                payload, result = self.run_case(route)
                prep = 5000 if route == 'stream' else 6000
                self.assertEqual(payload['handlerPrepareMs'], prep)
                self.assertEqual(payload['handlerChatInputsMs'], 2000)
                self.assertEqual(payload['handlerBotPrepareMs'], 3000)
                self.assertEqual(payload.get('handlerSessionMs'), None if route == 'stream' else 1000)
                self.assertEqual(payload['firstTokenMs'], 4000)
                self.assertEqual(payload['latencyMs'], 9000)
                self.assertEqual(payload['handlerFirstTokenMs'], prep + 4000)
                self.assertEqual(payload['handlerGenerationEndMs'], prep + 9000)
                if route == 'proxy':
                    self.assertEqual(result, {'answer': 'answer'})
                else:
                    self.assertEqual(result[0], {'type': 'token', 'content': 'answer'})
                    self.assertEqual(result[-1]['type'], 'done')

    def test_no_token_does_not_invent_ttft(self):
        for route in ('proxy', 'proxy_stream', 'stream'):
            for mode in ('empty', 'error'):
                with self.subTest(route=route, mode=mode):
                    payload, _ = self.run_case(route, mode)
                    self.assertNotIn('firstTokenMs', payload)
                    self.assertNotIn('handlerFirstTokenMs', payload)
                    prep = 5000 if route == 'stream' else 6000
                    self.assertEqual(payload['handlerGenerationEndMs'], prep + (4000 if mode == 'error' else 9000))

    def test_snapshot_failure_preserves_handler_metrics(self):
        for route in ('proxy', 'proxy_stream', 'stream'):
            with self.subTest(route=route):
                payload, _ = self.run_case(route, broken_snapshot=True)
                self.assertIn('handlerFirstTokenMs', payload)
                self.assertIn('handlerGenerationEndMs', payload)

    def test_legacy_direct_generator_call_is_compatible(self):
        payload, _ = self.run_case('direct')
        self.assertEqual(payload['firstTokenMs'], 4000)
        self.assertFalse(any(key.startswith('handler') for key in payload))
