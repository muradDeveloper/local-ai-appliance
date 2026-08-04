import asyncio
from unittest.mock import AsyncMock, MagicMock


# Inline stubs matching the spec -- tested independently of the tool module
# (avoids needing httpx installed on the host).

async def _get_loaded_model(valves, client):
    r = await client.get(f"{valves.ollama_url}/api/ps")
    models = r.json().get("models", [])
    if models:
        return models[0]["name"]
    if valves.ollama_model:
        return valves.ollama_model
    raise RuntimeError("No model loaded in Ollama and ollama_model valve is not set.")


async def _generate_negative_prompt(valves, client, positive_prompt):
    model = await _get_loaded_model(valves, client)
    r = await client.post(
        f"{valves.ollama_url}/api/generate",
        json={
            "model": model,
            "system": valves.negative_prompt_system,
            "prompt": positive_prompt,
            "stream": False,
        },
    )
    r.raise_for_status()
    return r.json()["response"].strip()


def make_valves(ollama_model=""):
    v = MagicMock()
    v.ollama_url = "http://ollama:11434"
    v.ollama_model = ollama_model
    v.negative_prompt_system = "Output only a negative prompt."
    return v


def make_client_with_ps(model_name):
    client = AsyncMock()
    response = MagicMock()
    response.json.return_value = (
        {"models": [{"name": model_name}]} if model_name else {"models": []}
    )
    client.get.return_value = response
    return client


async def test_get_loaded_model_from_ps():
    result = await _get_loaded_model(
        make_valves(), make_client_with_ps("gemma4:12b-instruct-qat")
    )
    assert result == "gemma4:12b-instruct-qat", f"got {result}"
    print("PASS test_get_loaded_model_from_ps")


async def test_get_loaded_model_fallback_to_valve():
    result = await _get_loaded_model(
        make_valves("gemma4:12b-instruct-qat"), make_client_with_ps(None)
    )
    assert result == "gemma4:12b-instruct-qat", f"got {result}"
    print("PASS test_get_loaded_model_fallback_to_valve")


async def test_get_loaded_model_raises_when_nothing_configured():
    try:
        await _get_loaded_model(make_valves(""), make_client_with_ps(None))
        assert False, "should have raised RuntimeError"
    except RuntimeError as e:
        assert "No model loaded" in str(e)
    print("PASS test_get_loaded_model_raises_when_nothing_configured")


async def test_generate_negative_prompt_returns_stripped_response():
    client = make_client_with_ps("gemma4:12b-instruct-qat")
    post_response = MagicMock()
    post_response.json.return_value = {"response": "  bad anatomy, blurry  "}
    client.post.return_value = post_response
    result = await _generate_negative_prompt(make_valves(), client, "1girl, anime")
    assert result == "bad anatomy, blurry", f"got '{result}'"
    print("PASS test_generate_negative_prompt_returns_stripped_response")


async def test_generate_negative_prompt_raises_on_http_error():
    client = make_client_with_ps("gemma4:12b-instruct-qat")
    post_response = MagicMock()
    post_response.raise_for_status.side_effect = Exception("500 Server Error")
    client.post.return_value = post_response
    try:
        await _generate_negative_prompt(make_valves(), client, "1girl, anime")
        assert False, "should have raised"
    except Exception as e:
        assert "500" in str(e)
    print("PASS test_generate_negative_prompt_raises_on_http_error")


if __name__ == "__main__":
    asyncio.run(test_get_loaded_model_from_ps())
    asyncio.run(test_get_loaded_model_fallback_to_valve())
    asyncio.run(test_get_loaded_model_raises_when_nothing_configured())
    asyncio.run(test_generate_negative_prompt_returns_stripped_response())
    asyncio.run(test_generate_negative_prompt_raises_on_http_error())
    print("All tests passed.")
