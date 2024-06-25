import logging

import httpx
from ray import serve
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse


@serve.deployment()
class VLLMPredictDeployment:
    async def __call__(self, request: Request) -> Response:
        url = "http://vllm-server:8001" + request.url.path

        try:
            async with httpx.AsyncClient(timeout=None) as client:
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
                    return Response(status_code=405)  # Method Not Allowed

            return Response(content=response.content, status_code=response.status_code,
                            headers=response.headers, media_type=response.headers.get('Content-Type'))
        except Exception as e:
            logging.exception("Failed to handle request: %s", e)
            return Response(content=str(e), status_code=500)

    async def handle_streaming_response(self, response):
        async def response_stream():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            except Exception as e:
                logging.exception("Streaming failed: %s", e)
                raise

        headers = dict(response.headers)
        headers.pop('Content-Length', None)

        return StreamingResponse(response_stream(), media_type=headers.get('Content-Type'), headers=headers)


# Deployment definition for Ray Serve
deployment = VLLMPredictDeployment.bind()
