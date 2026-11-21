# セキュリティ

## 脆弱性の報告

GitHub リポジトリ公開時に非公開脆弱性報告を有効にする予定です。有効化後は、リポジトリのセキュリティ画面で **Report a vulnerability** を選び、影響と再現条件を報告してください。再現例の認証情報や個人情報は伏せてください。公開 Issue に脆弱性の詳細を載せないでください。 [GitHub の非公開報告手順](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately)

## 秘密の保存

ローカルの `.env` または macOS Keychain を使用します。webhook の送信キーは Keychain を推奨します。伝書鳩の Agent ID は環境変数 `GROKWATCH_AGENT_ID` で渡し、実値は公開資料に記録しません。設定例には空欄またはプレースホルダを使います。

## ログ

記録する項目は状態、エラー種別、処理時間などの運用メタデータに絞ります。認証情報、Agent ID、端末固有 ID、ローカル IP、家庭内のパス、個人情報は出力前に `[伏字]` に置換します。認証ヘッダ、webhook URL、返信トークン、音声、会話本文は記録対象から外します。共有前にログと添付資料を確認します。
