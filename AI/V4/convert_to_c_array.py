"""Convert the verified V4 INT8 model to the firmware C array."""

from V4.runtime import configure_shared_contract

configure_shared_contract()

from src.convert_to_c_array import main


if __name__ == "__main__":
    main()

