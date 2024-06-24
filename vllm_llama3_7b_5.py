import httpx
from ray import serve
from starlette.requests import Request
from starlette.responses import Response


@serve.deployment(ray_actor_options={"num_gpus": 1})
class VLLMPredictDeployment:
    async def __call__(self, request: Request) -> Response:
        request_dict = await request.json()

        url = "http://localhost:8001/v1/completions"

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=request_dict)
            return Response(content=response.text, media_type="application/json")


# Deployment definition for Ray Serve
deployment = VLLMPredictDeployment.bind()
