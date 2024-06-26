"""
Example of a vLLM prompt completion service based on the Falcon-7b LLM
to get deployed on Ray Serve.

Adapted from the AnyScale team's repository
https://github.com/ray-project/ray/blob\
/cc983fc3e64c1ba215e981a43dd0119c03c74ff1/doc/source/serve/doc_code/vllm_example.py
"""

import json
import time
import uuid
from typing import AsyncGenerator

from fastapi import BackgroundTasks
from ray import serve
from starlette.requests import Request
from starlette.responses import StreamingResponse, Response
from vllm.engine.arg_utils import AsyncEngineArgs
from vllm.engine.async_llm_engine import AsyncLLMEngine
from vllm.sampling_params import SamplingParams
from vllm.utils import random_uuid


@serve.deployment(ray_actor_options={"num_gpus": 1})
class VLLMPredictDeployment:
    def __init__(self, **kwargs):
        args = AsyncEngineArgs(**kwargs)
        self.engine = AsyncLLMEngine.from_engine_args(args)

    async def stream_results(self, results_generator) -> AsyncGenerator[bytes, None]:
        num_returned = 0
        async for request_output in results_generator:
            text_outputs = [output.text for output in request_output.outputs]
            assert len(text_outputs) == 1
            text_output = text_outputs[0][num_returned:]
            ret = {"text": text_output}
            yield (json.dumps(ret) + "\n").encode("utf-8")
            num_returned += len(text_output)

    async def may_abort_request(self, request_id) -> None:
        await self.engine.abort(request_id)

    async def __call__(self, request: Request) -> Response:
        """Generate completion for the request.

        The request should be a JSON object with the following fields:
        - prompt: the prompt to use for the generation.
        - stream: whether to stream the results or not.
        - other fields: the sampling parameters (See `SamplingParams` for details).
        """
        request_dict = await request.json()
        if isinstance(request_dict, list):
            request_dict = request_dict[0]
        prompt = request_dict.pop("prompt")
        stream = request_dict.pop("stream", False)
        # model can´t be processed by ray
        request_dict.pop("model", None)
        request_dict.pop("logit_bias", None)
        # sampling_params = SamplingParams(**request_dict)
        sampling_params = SamplingParams()
        request_id = random_uuid()
        results_generator = self.engine.generate(prompt, sampling_params, request_id)
        if stream:
            background_tasks = BackgroundTasks()
            # Using background_taks to abort the the request
            # if the client disconnects.
            background_tasks.add_task(self.may_abort_request, request_id)
            return StreamingResponse(
                self.stream_results(results_generator), background=background_tasks
            )

        # Non-streaming case
        final_output = None
        async for request_output in results_generator:
            if await request.is_disconnected():
                # Abort the request if the client disconnects.
                await self.engine.abort(request_id)
                return Response(status_code=499)
            final_output = request_output

        assert final_output is not None
        prompt = final_output.prompt
        # text_outputs = [prompt + output.text for output in final_output.outputs]

        ret = {
            "id": uuid.uuid4(),
            "object": "chat.completion",
            "created": time.time(),
            "model": "meta-llama/Meta-Llama-3-8B-Instruct",
            "system_fingerprint": "fp_" + str(uuid.uuid4()),
            "choices": [
                {
                    "message": {
                        "role": "system",
                        "content": output.text,
                    },
                    "index": i,
                    "logprobs": None,
                    "finish_reason": "stop",
                }
                for i, output in enumerate(final_output.outputs)
            ],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": sum([len(output.text) for output in final_output.outputs]) * 2,
                "total_tokens": len(prompt.split()) + sum([len(output.text) for output in final_output.outputs]) * 2,
            },
        }

        return Response(content=json.dumps(ret))


# Deployment definition for Ray Serve
deployment = VLLMPredictDeployment.bind(
    model="meta-llama/Meta-Llama-3-8B-Instruct",
    trust_remote_code=True,
    gpu_memory_utilization=0.95,
    tensor_parallel_size=1,
)
