# 進捗

## 2026-11-21（JST）

| 日時 | 内容 | コマンド | 結果 | 次 |
| --- | --- | --- | --- | --- |
| 19:38 | 開発指示書（非公開）を受領 | — | Phase 1 の公開前準備と Phase 2 の調査を開始 | 公開先と参照実装を確認 |
| 19:40 | GitHub 公開 API でオーナーの `GrokWatch` を照会 | `GET /repos/{owner}/GrokWatch` | HTTP 404。GitHub CLI は未ログインのため、同名の非公開リポジトリの有無は未確認 | 認証済み環境で確認 |
| 19:40 | 参照リポジトリ 3 件を取得 | `git clone` | 参照目的で取得し、ライセンスを確認 | 採用候補の条件を記録 |
| 19:45 | Mac mini 環境の読み取り専用監査 | — | 結果を [環境](ENVIRONMENT.md) に要約。GrokWatch の作業者は Mac mini に触れていない | 検証計画に反映 |
| 19:45〜19:52 | ESP-IDF と gitleaks を導入 | `install.sh esp32s3`、`gitleaks version` | ESP-IDF v5.5.4 の導入完了と gitleaks 8.30.1 を確認 | 上流ビルドと公開前検査を実行 |
| 19:48〜19:52 | 開発エージェントが初期ファイルと調査文書を作成 | — | 初回コミット候補を作成 | 検査とレビュー |
| 19:52 | ステージ済み差分とファイルの検査 | `gitleaks git --pre-commit --staged`、`bash scripts/check_pii.sh` | 両方通過。合成データでは検出を確認 | 公開前レビュー |
| 19:54 | groki-bot の StopWatch 向け上流ビルドを再現 | `make build BOARD=stopwatch`（上流の再現コマンド） | M5GFX 0.3.0 ではヘッダー不在で失敗。0.2.30 に固定すると成功。詳細は [調査](RESEARCH.md) に記録 | GrokWatch のビルドは Phase 4 で検証 |
| 19:55 | 初回コミット候補のレビュー | — | high 2 件を履歴検査と公開文書の修正で解消 | 修正後の候補を再検査 |
| 20:24 | オーナーの承認を受けて公開 | `gh repo create`（Public）、`git push`（main） | 31 ファイルを公開。秘密・個人情報の検査が CI で成功 | 伝書鳩の webhook 仕様を作成し、Phase 3 を開始 |
| 21:10 | Phase 3〜4 の gateway・bridge 修正と CI 統合。作業主体は開発エージェント | `ctest` 通常・ASan/UBSan、`uv run --locked pytest`（3.11 / 3.13）、`idf.py build`、秘密・PII 検査 | ctest は各 57 件、pytest は各 119 件通過。生成アプリは 1,195,744 バイト。[テスト報告](TEST_REPORT.md) | GitHub Actions の実行、Phase 5 の端末確認、Phase 6 の Mac mini と伝書鳩の確認 |
| 21:21 | PR #1（`feat/phase3`）レビュー 1 回目 | — | high 1 件の指摘を確認 | 指定された指摘の回帰テストと修正 |
| 21:37 | NVS を廃止し、WS・webhook・ログ・タッチ・再生・仕様の指摘を修正 | `ctest` 通常・ASan/UBSan、`uv run pytest`（3.11 / 3.13）、`idf.py build`、`bash scripts/check_pii.sh` | ctest は各 60 件、pytest は各 132 件通過。生成アプリは 1,187,056 バイト。[テスト報告](TEST_REPORT.md) | 再レビューと Phase 5 の端末確認 |
| 21:43 | CI の firmware-build（クリーン環境）の失敗を修正 | `idf.py set-target esp32s3 && idf.py build`（追跡ファイルだけを展開した新しい場所） | 成功。`94b8808` の CI は全ジョブ成功 | 再レビューの結果を確認 |
| 21:45 | PR #1 レビュー 2 回目 | — | high なし、mid 5 件を確認 | 残った mid の修正。Phase 5 は書き込みの承認後 |
| 22:03 | PR #1 2 回目レビューの残件を修正。作業主体は開発エージェント | 通常・ASan/UBSan ctest、pytest（3.13 / 3.11）、クリーンソース `idf.py set-target esp32s3`・`idf.py build`、`bash scripts/check_pii.sh` | ctest は各 65 件、pytest は各 137 件通過。アプリは 1,188,224 バイト。[テスト報告](TEST_REPORT.md) | Phase 5 の端末確認 |
| 22:18〜 | 3 回目レビューの残件と Mac mini 設置ファイルを準備。作業主体は開発エージェント | 通常・ASan/UBSan ctest、pytest（3.13 / 3.11）、ESP-IDF ビルド、shellcheck、秘密・PII 検査 | 結果は[最新のテスト報告](TEST_REPORT.md)に記録。Mac mini と実機には未接触 | オーナー承認後の設置、実機確認 |
