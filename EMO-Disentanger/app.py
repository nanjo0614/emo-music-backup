import os
import random
import re

import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GEN_DIR = os.path.join(BASE_DIR, "generation", "emopia_functional_two")

# UI表示名 → Qコード
QUADRANTS = {
    "Q1（高覚醒・ポジティブ）": "Q1",
    "Q2（高覚醒・ネガティブ）": "Q2",
    "Q3（低覚醒・ネガティブ）": "Q3",
    "Q4（高覚醒・ポジティブ）": "Q4",
}

# Qコード → valence ラベル（ファイル名の Positive / Negative と対応）
VALENCE_BY_Q = {
    "Q1": "Positive",
    "Q4": "Positive",
    "Q2": "Negative",
    "Q3": "Negative",
}

# --- セッション状態の初期化 ---
if "loaded_tracks" not in st.session_state:
    st.session_state["loaded_tracks"] = []  # wav のパス一覧
if "loaded_q_code" not in st.session_state:
    st.session_state["loaded_q_code"] = None


def list_wavs_for_quadrant(q_code: str):
    """samp_XX_Q?_full.wav を列挙"""
    if not os.path.exists(GEN_DIR):
        return []

    files = []
    for fname in os.listdir(GEN_DIR):
        if fname.endswith(f"_{q_code}_full.wav"):
            files.append(os.path.join(GEN_DIR, fname))

    files.sort()
    return files


def extract_sample_id_from_wav(wav_path: str) -> str:
    """
    samp_06_Q1_full.wav → "06" を取り出す。
    """
    base = os.path.basename(wav_path)
    m = re.match(r"samp_(\d+)_Q[1-4]_full\.wav", base)
    if not m:
        return None
    return m.group(1)


def parse_bar_chords_from_roman(path: str):
    """
    EMO-Disentanger の *_roman.txt から
    小節ごとの代表コード（その小節で最初に現れる Chord_***）を抽出する。

    戻り値: [(bar_index(int), chord_name(str)), ...]
      bar_index は 1 始まり。
    """
    bar_index = -1  # まだ小節に入ってない状態
    bar_chords = []  # index: 0-based(=小節-1), value: chord(str) or None

    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
    except Exception as e:
        return [], f"ファイル読み込みエラー: {e}"

    for line in lines:
        if line.startswith("Key_"):
            # 調性情報。ここでは無視（必要なら後で使える）
            continue
        if line.startswith("Bar_"):
            # 新しい小節の開始
            bar_index += 1
            bar_chords.append(None)
            continue
        if line.startswith("Chord_") and bar_index >= 0:
            chord_name = line[len("Chord_"):]
            # その小節で最初に出てきたコードだけを採用
            if bar_chords[bar_index] is None:
                bar_chords[bar_index] = chord_name

    result = []
    for i, chord in enumerate(bar_chords, start=1):
        if chord is None:
            # コードラベルがない小節はスキップ（ほぼない想定）
            continue
        result.append((i, chord))

    return result, None


def load_chord_progression(sample_id: str, q_code: str) -> str:
    """
    サンプルIDとQから、対応する roman.txt / txt を読み込み、
    小節ごとの代表コードと、矢印でつないだ進行をテキストで返す。

      例） 小節 1: I_M
           小節 2: I_M
           小節 3: VI_m
           小節 4: III_m7
           ...
           コード進行（小節ごと）:
           I_M→I_M→VI_m→III_m7→...
    """
    if sample_id is None:
        return "コード進行ファイルを特定できませんでした。"

    valence = VALENCE_BY_Q.get(q_code)
    if valence is None:
        return "valence が特定できませんでした。"

    # roman優先
    roman_name = f"samp_{sample_id}_{valence}_roman.txt"
    roman_path = os.path.join(GEN_DIR, roman_name)

    bar_info = None
    if os.path.exists(roman_path):
        bars, err = parse_bar_chords_from_roman(roman_path)
        if err:
            return err
        if bars:
            bar_info = bars

    # roman が使えなかった場合は、従来通りプレーンtxtをそのまま返すフォールバック
    if bar_info is None:
        plain_name = f"samp_{sample_id}_{valence}.txt"
        plain_path = os.path.join(GEN_DIR, plain_name)
        if os.path.exists(plain_path):
            try:
                with open(plain_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"コード進行の読み込み中にエラー: {e}"
        return "対応するコード進行ファイルが見つかりませんでした。"

    # ここから整形して人間に読める形にする
    # bar_info: [(bar_index, chord_name), ...]
    lines = []
    for bar_idx, chord in bar_info:
        lines.append(f"小節 {bar_idx}: {chord}")

    # 矢印でつないだ進行（小節ごと、繰り返しもそのまま）
    progression = "→".join(chord for (_, chord) in bar_info)

    lines.append("")  # 空行
    lines.append("コード進行（小節ごと）:")
    lines.append(progression)

    return "\n".join(lines)


def main():
    st.title("EMO-Disentanger Emotion Player（デモ）")

    st.write(
        "感情象限 Q1〜Q4 のいずれかを選ぶと、その象限に対応した曲をランダムに最大10曲表示・再生します。"
        "各曲には対応するコード進行（functional / roman表記）も表示します。"
    )

    label = st.selectbox("感情象限を選択", list(QUADRANTS.keys()))
    q_code = QUADRANTS[label]

    n_tracks = st.slider("表示する曲数", min_value=1, max_value=10, value=10, step=1)

    # ボタンが押されたときだけ、状態を更新する
    if st.button("曲を読み込む"):
        wav_files = list_wavs_for_quadrant(q_code)
        if not wav_files:
            st.error(
                f"{q_code} の wav ファイルが見つかりません。先に MIDI→wav 変換スクリプトを実行してください。"
            )
        else:
            if len(wav_files) > n_tracks:
                wav_files = random.sample(wav_files, n_tracks)

            # セッション状態に保存（ここでは表示しない）
            st.session_state["loaded_tracks"] = wav_files
            st.session_state["loaded_q_code"] = q_code

    # ここからは「セッションに保存されているもの」を常に表示
    loaded_tracks = st.session_state.get("loaded_tracks", [])
    loaded_q = st.session_state.get("loaded_q_code", None)

    if loaded_tracks and loaded_q is not None:
        st.success(f"{loaded_q} の曲を {len(loaded_tracks)} 曲表示します。")

        for i, wav_path in enumerate(loaded_tracks, start=1):
            base = os.path.basename(wav_path)
            midi_path = wav_path.replace(".wav", ".mid")
            sample_id = extract_sample_id_from_wav(wav_path)
            chords = load_chord_progression(sample_id, loaded_q)

            st.markdown(f"### {i}. {base}")

            # オーディオ再生
            with open(wav_path, "rb") as f:
                audio_bytes = f.read()
            st.audio(audio_bytes, format="audio/wav")

            # MIDI ダウンロードボタン（ここを押しても状態は保持される）
            if os.path.exists(midi_path):
                with open(midi_path, "rb") as f:
                    midi_bytes = f.read()
                st.download_button(
                    label="MIDI をダウンロード",
                    data=midi_bytes,
                    file_name=os.path.basename(midi_path),
                    mime="audio/midi",
                    key=f"midi_dl_{i}",  # 各ボタンに一意のキー
                )

            # コード進行表示
            with st.expander("コード進行を表示（roman）"):
                st.text(chords)


if __name__ == "__main__":
    main()
