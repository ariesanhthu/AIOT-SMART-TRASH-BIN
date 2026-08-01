"""Run clean float/INT8 evaluation under the V5 four-class contract."""

from V5.runtime import configure_shared_contract

configure_shared_contract()

from src.evaluate_model import main  # noqa: E402


if __name__ == "__main__":
    main()
