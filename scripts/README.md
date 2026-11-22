# スクリプト

`bash scripts/scan_secrets.sh` は、gitleaks の標準ルールと GrokWatch 用ルールでステージ済み差分と既存の全 Git 履歴を検査します。`bash scripts/check_pii.sh` はステージ済みファイルの名前と内容を検査し、`--history-paths` を指定するとバイナリを含む履歴上のファイル名と形式も検査します。初回コミット前はステージ済みの検査を行います。検査に失敗すると終了コードは非 0 になります。

登録できるファイルは Markdown、シェルスクリプト、YAML、TOML、ルートの `LICENSE` と `.gitignore`、`config/.env.example` です。形式を追加する際は、素材の権利と公開範囲を確認してから検査の許可リストを更新します。

`release_version.py` は firmware・gateway・bridge の版番号が一致することを確かめて表示します。`main` への push で CI が成功すると、`.github/workflows/release-tag.yml` がこの版番号で `v<版>` タグを付けます（既にあれば何もしない）。
