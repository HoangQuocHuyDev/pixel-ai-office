from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


def check_connection() -> bool:
    try:
        from app.db.session import engine

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except ValidationError:
        print("Database connection failed: DATABASE_URL is missing or invalid.")
        return False
    except SQLAlchemyError:
        print("Database connection failed: unable to connect to PostgreSQL.")
        return False

    print("Database connection successful.")
    return True


def main() -> int:
    return 0 if check_connection() else 1


if __name__ == "__main__":
    raise SystemExit(main())
