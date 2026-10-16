"""Offline OpenAI transport fixture shared by engine and HTTP regressions."""

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from openai.types.chat import ChatCompletion

from agent_orchestrator import engine
from contracts.patch_schemas import PatchProposal


def install_offline_patch_client(test_case: unittest.TestCase) -> AsyncMock:
    """Keep the real proposer and validators while replacing its network client.

    Every test uses a dummy key even when a developer has configured live access.
    The completion represents the accepted synthetic repair; callers can still
    override its content to exercise each independent downstream guardrail.
    """
    environment = patch.dict(os.environ, {"OPENAI_API_KEY": "offline-test-key"})
    environment.start()
    test_case.addCleanup(environment.stop)

    proposal = PatchProposal(
        patch_id="offline-semantic-repair",
        file_path=engine._SIM_FILE,
        diff=engine._SIM_DIFF,
        fingerprint_id="FP_WARP_SIZE",
        lines_added=1,
        lines_deleted=1,
        explanation="Replace the fixed lane count with the target warpSize.",
        allowlisted=True,
        modifies_dependencies=False,
        modifies_public_api=False,
        modifies_tests_or_tolerances=False,
    )
    completion = ChatCompletion(
        id="offline-completion",
        created=0,
        model="offline-test-model",
        object="chat.completion",
        choices=[{
            "index": 0,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": proposal.model_dump_json(),
                "refusal": None,
            },
        }],
    )
    client = MagicMock(name="offline_openai_client")
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    create_completion = AsyncMock(return_value=completion)
    client.chat.completions.create = create_completion
    factory = patch.object(engine, "AsyncOpenAI", return_value=client)
    factory.start()
    test_case.addCleanup(factory.stop)
    return create_completion
