from mkvsd.classifier import classify_track
from mkvsd.models import SubtitleTrack


def mk(index, name="", language="spa", ietf="", default=False, forced=False):
    return classify_track(SubtitleTrack(
        id=index, index=index, uid=1000 + index, name=name, language=language,
        ietf=ietf, codec="SubRip/SRT", default=default, forced=forced,
    ))
