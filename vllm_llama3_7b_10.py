import httpx
from ray import serve
from starlette.requests import Request
from starlette.responses import Response


@serve.deployment()
class VLLMPredictDeployment:
    async def __call__(self, request: Request) -> Response:
        url = "http://vllm-server:8001" + request.url.path

        async with httpx.AsyncClient() as client:
            if request.method == "GET":
                response = await client.get(url, params=request.query_params)
            elif request.method == "POST":
                body = await request.json()
                response = await client.post(url, json=body)
            else:
                # Add more methods as needed
                return Response(status_code=405)  # Method Not Allowed

        return Response(content=response.content, status_code=response.status_code, headers=response.headers, media_type=response.headers.get('Content-Type'))


# Deployment definition for Ray Serve
deployment = VLLMPredictDeployment.bind()