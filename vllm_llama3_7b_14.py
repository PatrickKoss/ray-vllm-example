import httpx
from ray import serve
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse


@serve.deployment()
class VLLMPredictDeployment:
    async def __call__(self, request: Request) -> Response:
        url = "http://vllm-server:8001" + request.url.path
        # url = "http://localhost:8001" + request.url.path

        async with httpx.AsyncClient() as client:
            if request.method == "GET":
                response = await client.get(url, params=request.query_params)
            elif request.method == "POST":
                body = await request.json()
                stream = body.pop("stream", False)
                if stream:
                    async with client.stream("POST", url, json=body) as response:
                        return await self.handle_streaming_response(response)
                else:
                    response = await client.post(url, json=body)
            else:
                # Add more methods as needed
                return Response(status_code=405)  # Method Not Allowed

        return Response(content=response.content, status_code=response.status_code, headers=response.headers,
                        media_type=response.headers.get('Content-Type'))

    async def handle_streaming_response(self, response):
        async def response_stream():
            async for chunk in response.aiter_bytes():
                yield chunk

        headers = dict(response.headers)
        headers.pop('Content-Length', None)

        return StreamingResponse(response_stream(), media_type=headers.get('Content-Type'), headers=headers)


# Deployment definition for Ray Serve
deployment = VLLMPredictDeployment.bind()
