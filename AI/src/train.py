try:
    from .train_cnn import main
except ImportError:
    from train_cnn import main


if __name__ == "__main__":
    main()
