import torch
from dotenv import load_dotenv
from pytubefix import YouTube

import whisper
from mcp.server.fastmcp import FastMCP

# from openai import OpenAI

load_dotenv(override=True)


mcp = FastMCP("server weather")


def download_yt(url="https://www.youtube.com/watch?v=-w53i6Ae-YM", path="."):
    yt = YouTube(url)

    ys = yt.streams.get_audio_only()
    ys.download(output_path=path, filename="audio.mp4")


def transcibe_audio(path: str = "audio.mp4"):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    model = whisper.load_model("medium", device=device)
    result = model.transcribe(path)

    return result["text"]


@mcp.tool(
    name="download_youtube_video",
    description="Descarga y transcribe un video de YouTube.",
)
async def download_youtube_video(url: str, path: str = ".") -> str:
    try:
        download_yt(url, path)

        # -------------
        # -------------

        # OPENAI

        # client = OpenAI(
        #     api_key=""
        # )
        # audio_file = open("audio.mp4", "rb")
        #
        # transcription = client.audio.transcriptions.create(
        #     model="gpt-4o-mini-transcribe",
        #     file=audio_file,
        #     response_format="text",
        # )
        #
        # -------------
        # -------------

        transcription = transcibe_audio()

        # print(transcription)

        return transcription
    except Exception as e:
        return f"Error al descargar el video: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
    # mcp.run(transport="streamable-http")
