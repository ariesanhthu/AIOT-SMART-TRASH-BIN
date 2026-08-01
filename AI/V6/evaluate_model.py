"""Evaluate float and full-INT8 models under the V6 contract."""

from V6.runtime import configure_shared_contract

configure_shared_contract()

from src.evaluate_model import main  # noqa: E402


if __name__ == "__main__":
    main()

