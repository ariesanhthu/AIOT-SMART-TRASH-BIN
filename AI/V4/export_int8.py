"""Run the shared verified INT8 exporter under the V4 contract."""

from V4.runtime import configure_shared_contract

configure_shared_contract()

from src.export_int8 import main


if __name__ == "__main__":
    main()

