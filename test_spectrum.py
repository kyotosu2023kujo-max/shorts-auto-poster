import os
import numpy as np
from PIL import Image, ImageDraw

def generate_demo_frames():
    output_folder = "demo_frames"
    os.makedirs(output_folder, exist_ok=True)
    
    # アイコンの読み込みと丸型マスク処理のテスト
    icon_path = "youtubeicon.png"
    try:
        icon_raw = Image.open(icon_path).convert('RGBA')
        icon_size = (110, 110)
        icon_raw = icon_raw.resize(icon_size, Image.Resampling.LANCZOS)
        
        mask = Image.new('L', icon_size, 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0, icon_size[0], icon_size[1]), fill=255)
        
        icon_img = Image.new('RGBA', icon_size, (0, 0, 0, 0))
        icon_img.paste(icon_raw, (0, 0), mask)
    except OSError:
        print(f"⚠️ {icon_path} が見つからないため、仮の青い丸アイコンを作成します")
        icon_size = (110, 110)
        icon_img = Image.new('RGBA', icon_size, (0, 0, 0, 0))
        draw_dummy = ImageDraw.Draw(icon_img)
        draw_dummy.ellipse((0, 0, icon_size[0], icon_size[1]), fill=(0, 100, 255, 255))

    num_bars = 48
    radius_base = 65
    max_bar_length = 80
    
    # ダミーの音量データ（0.0〜1.0）で5フレーム分のデモ画像を生成
    dummy_volumes = [0.2, 0.5, 0.9, 0.6, 0.3]
    
    for i, volume in enumerate(dummy_volumes):
        comp_img = Image.new('RGBA', (360, 360), (0, 0, 0, 0))
        draw = ImageDraw.Draw(comp_img)
        
        center_x = comp_img.width / 2
        center_y = comp_img.height / 2

        # 放射状のスペクトラム棒を描画
        for b in range(num_bars):
            angle = (360 / num_bars) * b
            rad = np.deg2rad(angle)
            
            bar_len = max(12, int(volume * max_bar_length))
            start_r = radius_base
            end_r = radius_base + bar_len
            
            start_x = center_x + start_r * np.cos(rad)
            start_y = center_y + start_r * np.sin(rad)
            end_x = center_x + end_r * np.cos(rad)
            end_y = center_y + end_r * np.sin(rad)
            
            bar_width = 5
            bar_color = (0, 240, 255, 220)
            
            draw.line([(start_x, start_y), (end_x, end_y)], fill=bar_color, width=bar_width)

        # アイコンを中央に配置
        if icon_img:
            icon_x = center_x - icon_size[0] / 2
            icon_y = center_y - icon_size[1] / 2
            comp_img.paste(icon_img, (int(icon_x), int(icon_y)), icon_img)

        frame_path = os.path.join(output_folder, f"demo_frame_{i}.png")
        comp_img.save(frame_path)
        print(f"💾 デモ画像を保存しました: {frame_path}")

if __name__ == "__main__":
    generate_demo_frames()
