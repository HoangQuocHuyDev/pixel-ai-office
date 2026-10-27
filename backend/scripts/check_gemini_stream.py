import asyncio
import sys
import time
from pathlib import Path

# Add backend directory to sys.path so app imports work when executed directly
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.schemas.ai import AIPromptRequest
from app.services.ai_service import AIService


async def main() -> int:
    settings = get_settings()

    print("=== Pixel AI Office: Gemini Streaming Verification ===")
    print(f"Provider: {settings.ai_provider}")
    print(f"Model: {settings.gemini_model}")
    print(f"Timeout: {settings.ai_request_timeout_seconds}s")
    print(f"Max Output Tokens: {settings.ai_max_output_tokens}")

    if not settings.gemini_api_key or not settings.gemini_api_key.get_secret_value().strip():
        print("\n[SKIPPED] GEMINI_API_KEY is not configured in .env or environment.")
        print("Set GEMINI_API_KEY in backend/.env to run live streaming tests.")
        return 0

    print("\nSending live test prompt to Gemini streaming API...")
    test_prompt = "Explain in 3 bullet points why autonomous AI agents are useful in an office simulation."

    ai_service = AIService()
    start_time = time.perf_counter()
    chunk_count = 0

    try:
        print("\n--- Streaming Response Start ---")
        async for chunk in ai_service.generate_response_stream(
            AIPromptRequest(
                prompt=test_prompt,
                system_instruction="You are a concise office simulation AI assistant.",
            )
        ):
            chunk_count += 1
            print(chunk, end="", flush=True)

        elapsed = time.perf_counter() - start_time
        print("\n--- Streaming Response End ---")
        print(f"\n[SUCCESS] Stream completed successfully.")
        print(f"Total Chunks: {chunk_count}")
        print(f"Elapsed Time: {elapsed:.2f}s")
        return 0

    except ApplicationError as exc:
        print(f"\n\n[ERROR] ({exc.status_code} - {exc.error_code}): {exc.message}")
        return 1
    except Exception as exc:
        print(f"\n\n[UNEXPECTED ERROR] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

