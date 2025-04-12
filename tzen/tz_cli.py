import typer
from typing import List

app = typer.Typer()

@app.command()
def start_session(
    directory: str,
    testcases: List[str],
    config_file: str,
):
    print(f"Starting session in directory: {directory}")
    print(f"Test cases to execute: {', '.join(testcases)}")
    print(f"Using configuration file: {config_file}")




if __name__ == "__main__":
    app()