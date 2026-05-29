import subprocess
import sys

import nltk


def main() -> None:
    for corpus in ("stopwords", "wordnet", "omw-1.4"):
        nltk.download(corpus, quiet=True)
    print("NLTK data ready.")

    subprocess.run(
        [sys.executable, "-m", "spacy", "download", "en_core_web_trf"],
        check=True,
    )
    print("spaCy model ready.")


if __name__ == "__main__":
    main()
