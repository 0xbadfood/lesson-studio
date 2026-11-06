import contextlib
import tempfile
import unittest
from unittest import mock

import anthropic

from scivid import llm


class DroppedStream(unittest.TestCase):
    def test_a_cut_stream_is_asked_again_without_spending_an_attempt(self):
        # 2026-11-06, the molecule index (Class 12 chapter 4): httpx2 cut the stream and the run stopped
        if not llm.SDK_DROPPED:
            self.skipTest('the SDK does not use httpx2 here')
        message = mock.Mock(stop_reason='end_turn', usage=mock.Mock(input_tokens=1, output_tokens=1),
                            content=[mock.Mock(type='text', text='{"ok": 1}')])
        message.to_dict.return_value = {}
        calls = []

        @contextlib.contextmanager
        def stream(**kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise llm.SDK_DROPPED[0]('peer closed connection without sending complete message body')
            yield mock.Mock(get_final_message=lambda: message)
        client = mock.Mock()
        client.beta.messages.stream = stream
        validated = []
        with tempfile.TemporaryDirectory() as root, mock.patch.object(llm.time, 'sleep'):
            claude = llm.Claude('claude-opus-5-5', root, api_key='k')
            with mock.patch.object(claude, '_client', return_value=(anthropic, client)):
                result = claude.call('x', 'p', validate=validated.append, attempts=1)
        self.assertEqual(result, {'ok': 1})
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(validated), 1)


if __name__ == '__main__':
    unittest.main()
