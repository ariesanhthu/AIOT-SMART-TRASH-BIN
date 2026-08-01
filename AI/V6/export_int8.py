"""Export V6 to a verified full-INT8 TFLite model."""

from V6.runtime import configure_shared_contract

configure_shared_contract()

from src.export_int8 import main  # noqa: E402


if __name__ == "__main__":
    main()

