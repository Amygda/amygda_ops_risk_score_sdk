import nltk


def main() -> None:
    for corpus in ("stopwords", "wordnet", "omw-1.4"):
        nltk.download(corpus, quiet=True)
    print("NLTK data ready.")


if __name__ == "__main__":
    main()
