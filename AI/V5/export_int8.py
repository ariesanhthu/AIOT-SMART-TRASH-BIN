"""Export and verify the V5 model as a full INT8 TFLite artifact."""

from V5.runtime import configure_shared_contract

configure_shared_contract()

from src.export_int8 import main  # noqa: E402


if __name__ == "__main__":
    main()
