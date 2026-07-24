"""Run float/INT8 evaluation under the V4 four-class contract."""

from V4.runtime import configure_shared_contract

configure_shared_contract()

from src.evaluate_model import main


if __name__ == "__main__":
    main()

