"""Convert the verified V5 INT8 model to the firmware C array."""

from V5.runtime import configure_shared_contract

configure_shared_contract()

from src.convert_to_c_array import main  # noqa: E402


if __name__ == "__main__":
    main()
