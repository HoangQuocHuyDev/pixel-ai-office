import asyncio
import sys
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

    print("=== Pixel AI Office: Gemini Provider Verification ===")
    print(f"Provider: {settings.ai_provider}")
    print(f"Model: {settings.gemini_model}")
    print(f"Timeout: {settings.ai_request_timeout_seconds}s")
    print(f"Max Output Tokens: {settings.ai_max_output_tokens}")

    if not settings.gemini_api_key or not settings.gemini_api_key.get_secret_value().strip():
        print("\n[SKIPPED] GEMINI_API_KEY is not configured in .env or environment.")
        print("Set GEMINI_API_KEY in backend/.env to run live API tests.")
        return 0

    print("\nSending live test prompt to Gemini API...")
    test_prompt = "Hello! Please answer in one short sentence: What is your primary purpose as an AI assistant?"

    ai_service = AIService()
    try:
        response = await ai_service.generate_response(
            AIPromptRequest(
                prompt=test_prompt,
                system_instruction="You are a helpful office manager AI assistant.",
            )
        )
        print("\n[SUCCESS] Response received from Gemini:")
        print(f"Provider: {response.provider}")
        print(f"Model: {response.model}")
        print(f"Content: {response.content.strip()}")
        if response.usage_metadata:
            print(f"Tokens Usage: {response.usage_metadata}")
        if response.finish_reason:
            print(f"Finish Reason: {response.finish_reason}")
        return 0
    except ApplicationError as exc:
        print(f"\n[ERROR] ({exc.status_code} - {exc.error_code}): {exc.message}")
        return 1
    except Exception as exc:
        print(f"\n[UNEXPECTED ERROR] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

