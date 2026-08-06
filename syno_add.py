import sys
from synology_download_station_agent.client import SynologyClient, SynologyClientError


def add_magnet(magnet_uri: str) -> str:
    """Helper function to add magnet link and return output string."""
    try:
        with SynologyClient() as client:
            client.add_magnet(magnet_uri)
            return "Task successfully added to Synology Download Station!"
    except SynologyClientError as e:
        return f"Failed to add task: {e}"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        magnet_link = sys.argv[1]
        print(add_magnet(magnet_link))
    else:
        print("Please provide a magnet link.")
