"""
設定管理クラス
ローカル環境とAWS環境の両方に対応した設定読み込み機能
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False

# データモデルをインポート
from src.models.data_models import (
    StockConfig, 
    WatchlistStock, 
    GoogleSheetsConfig
)
from src.utils.validators import ConfigValidator, ValidationError
from src.services.parameter_store_service import (
    ParameterStoreService, 
    ParameterStoreConfig
)

logger = logging.getLogger(__name__)


@dataclass
class GeminiConfig:
    """Gemini AI設定"""
    api_key: str
    model: str = "gemini-pro"
    max_tokens: int = 1000
    temperature: float = 0.7


@dataclass
class SlackConfig:
    """Slack設定"""
    webhook_url: str
    channel: str = "#stock-analysis"
    username: str = "Stock Analysis Bot"


@dataclass
class AppConfig:
    """アプリケーション設定"""
    environment: str
    log_level: str
    google_sheets: GoogleSheetsConfig
    gemini: GeminiConfig
    slack: SlackConfig
    stocks: List[StockConfig] = field(default_factory=list)
    watchlist: List[WatchlistStock] = field(default_factory=list)
    aws_region: str = "ap-northeast-1"
    test_mode: bool = False
    mock_external_apis: bool = False


class ConfigManager:
    """設定管理クラス（強化版）"""
    
    def __init__(self, region_name: str = "ap-northeast-1"):
        self.environment = os.getenv("ENVIRONMENT", "local")
        self.logger = logging.getLogger(__name__)
        self._config: Optional[AppConfig] = None
        self._parameter_store_service = None
        
        # Parameter Storeサービスの初期化
        if AWS_AVAILABLE and self.environment in ["aws", "test"]:
            try:
                self._parameter_store_service = ParameterStoreService(region_name)
                if self._parameter_store_service.is_available:
                    self.logger.info("Parameter Store統合が有効になりました")
                else:
                    self.logger.warning("Parameter Storeは利用できませんが、処理を続行します")
            except Exception as e:
                self.logger.warning(f"Parameter Store初期化に失敗: {e}")
                self._parameter_store_service = None
    
    def get_config(self) -> AppConfig:
        """設定を取得"""
        if self._config is None:
            self._config = self._load_config()
        return self._config
    
    def _load_config(self) -> AppConfig:
        """環境に応じて設定を読み込み"""
        self.logger.info(f"環境 '{self.environment}' の設定を読み込み中...")
        
        if self.environment == "aws":
            return self._load_aws_config()
        else:
            return self._load_local_config()
    
    def _load_local_config(self) -> AppConfig:
        """ローカル環境の設定を読み込み"""
        self.logger.info("ローカル環境設定を読み込み中...")
        
        # 必須設定のチェック
        required_vars = [
            "GOOGLE_SHEETS_ID",
            "GEMINI_API_KEY",
            "SLACK_WEBHOOK_URL"
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"必須環境変数が設定されていません: {', '.join(missing_vars)}")
        
        # Google Sheets設定
        google_sheets_config = GoogleSheetsConfig(
            spreadsheet_id=os.getenv("GOOGLE_SHEETS_ID"),
            credentials_json_path=os.getenv("GOOGLE_CREDENTIALS_JSON_PATH", "credentials.json")
        )
        
        # Gemini設定
        gemini_config = GeminiConfig(
            api_key=os.getenv("GEMINI_API_KEY"),
            model=os.getenv("GEMINI_MODEL", "gemini-pro")
        )
        
        # Slack設定
        slack_config = SlackConfig(
            webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
            channel=os.getenv("SLACK_CHANNEL", "#stock-analysis")
        )
        
        return AppConfig(
            environment=self.environment,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            google_sheets=google_sheets_config,
            gemini=gemini_config,
            slack=slack_config,
            aws_region=os.getenv("AWS_REGION", "ap-northeast-1"),
            test_mode=os.getenv("TEST_MODE", "false").lower() == "true",
            mock_external_apis=os.getenv("MOCK_EXTERNAL_APIS", "false").lower() == "true"
        )
    
    def _load_aws_config(self) -> AppConfig:
        """AWS環境の設定を読み込み（強化版）"""
        self.logger.info("AWS環境設定を読み込み中...")
        
        if not self._parameter_store_service or not self._parameter_store_service.is_available:
            # フォールバック: 環境変数から読み込み
            self.logger.warning("Parameter Storeが利用できません。環境変数から設定を読み込みます。")
            return self._load_local_config()
        
        try:
            # Parameter Storeから一括取得
            parameters = self._get_aws_parameters()
            
            # 設定の検証
            validation_errors = ParameterStoreConfig.validate_parameter_structure(parameters)
            if validation_errors:
                self.logger.error("Parameter Store設定検証エラー:")
                for error in validation_errors:
                    self.logger.error(f"  - {error}")
                raise ValueError("Parameter Store設定が無効です")
            
            # 設定オブジェクトの構築
            return self._build_config_from_parameters(parameters)
            
        except Exception as e:
            self.logger.error(f"AWS設定の読み込みに失敗: {e}")
            
            # 重大エラーの場合は再試行しない
            if isinstance(e, (PermissionError, ValueError)):
                raise
            
            # 一時的なエラーの場合はフォールバック
            self.logger.warning("フォールバックとして環境変数から設定を読み込みます")
            return self._load_local_config()
    
    def _get_aws_parameters(self) -> Dict[str, str]:
        """Parameter Storeから必要なパラメータを一括取得"""
        parameters = {}
        
        # 必須パラメータを順次取得
        param_configs = [
            ("google_sheets_id", False),
            ("google_credentials", True),
            ("gemini_api_key", True),
            ("slack_webhook", True),
            ("slack_channel", False),
            ("log_level", False)
        ]
        
        for param_key, is_secure in param_configs:
            param_path = ParameterStoreConfig.get_parameter_path(param_key)
            try:
                value = self._parameter_store_service.get_parameter(
                    param_path, 
                    decrypt=is_secure,
                    use_cache=True
                )
                parameters[param_key] = value
                self.logger.debug(f"パラメータ取得成功: {param_key}")
            except ValueError:
                # 必須パラメータの場合はエラー
                if param_key in ["google_sheets_id", "gemini_api_key", "slack_webhook"]:
                    raise
                # オプションパラメータの場合はデフォルト値を使用
                self.logger.warning(f"オプションパラメータが見つかりません: {param_key}")
            except Exception as e:
                self.logger.error(f"パラメータ取得エラー ({param_key}): {e}")
                if param_key in ["google_sheets_id", "gemini_api_key", "slack_webhook"]:
                    raise
        
        return parameters
    
    def _build_config_from_parameters(self, parameters: Dict[str, str]) -> AppConfig:
        """Parameter Storeのパラメータから設定オブジェクトを構築"""
        # Google Sheets設定
        google_sheets_config = GoogleSheetsConfig(
            spreadsheet_id=parameters["google_sheets_id"]
        )
        
        # Google認証情報の処理
        if "google_credentials" in parameters:
            # JSON文字列をファイルに保存するかメモリで保持するかを決定
            credentials_data = parameters["google_credentials"]
            try:
                # JSON形式の検証
                json.loads(credentials_data)
                google_sheets_config.credentials_json_path = "memory"  # メモリ保持を示す
            except json.JSONDecodeError:
                self.logger.warning("Google認証情報のJSON形式が無効です")
        
        # Gemini設定
        gemini_config = GeminiConfig(
            api_key=parameters["gemini_api_key"],
            model=os.getenv("GEMINI_MODEL", "gemini-pro")
        )
        
        # Slack設定
        slack_config = SlackConfig(
            webhook_url=parameters["slack_webhook"],
            channel=parameters.get("slack_channel", "#stock-analysis")
        )
        
        return AppConfig(
            environment=self.environment,
            log_level=parameters.get("log_level", "INFO"),
            google_sheets=google_sheets_config,
            gemini=gemini_config,
            slack=slack_config,
            aws_region=os.getenv("AWS_REGION", "ap-northeast-1"),
            test_mode=os.getenv("TEST_MODE", "false").lower() == "true",
            mock_external_apis=os.getenv("MOCK_EXTERNAL_APIS", "false").lower() == "true"
        )
    
    def validate_config(self, config: AppConfig) -> bool:
        """設定の妥当性を検証（強化版）"""
        errors = []
        
        try:
            # Google Sheets設定の検証
            try:
                ConfigValidator.validate_google_sheets_id(config.google_sheets.spreadsheet_id)
            except ValidationError as e:
                errors.append(f"Google Sheets設定: {str(e)}")
            
            # データクラス内の検証も実行
            if not config.google_sheets.is_valid:
                errors.append("Google Sheets設定に無効な値が含まれています")
            
            # Gemini設定の検証
            try:
                ConfigValidator.validate_api_key(config.gemini.api_key, "Gemini")
            except ValidationError as e:
                errors.append(f"Gemini設定: {str(e)}")
            
            # Slack設定の検証
            try:
                ConfigValidator.validate_webhook_url(config.slack.webhook_url)
            except ValidationError as e:
                errors.append(f"Slack設定: {str(e)}")
            
            # 環境固有の検証
            if config.environment not in ["local", "aws", "test"]:
                errors.append(f"無効な環境設定: {config.environment}")
            
            # ログレベルの検証
            valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if config.log_level.upper() not in valid_log_levels:
                errors.append(f"無効なログレベル: {config.log_level}")
            
            if errors:
                error_message = "設定検証エラー:\n" + "\n".join(f"- {error}" for error in errors)
                self.logger.error(error_message)
                return False
            
            self.logger.info("設定の検証が完了しました")
            return True
            
        except Exception as e:
            self.logger.error(f"設定検証中に予期しないエラーが発生: {e}")
            return False
    
    def get_credentials_path(self) -> Path:
        """Google Sheets認証情報ファイルのパスを取得"""
        config = self.get_config()
        creds_path = Path(config.google_sheets.credentials_json_path)
        
        if not creds_path.is_absolute():
            # 相対パスの場合はプロジェクトルートからの相対パス
            project_root = Path(__file__).parent.parent.parent
            creds_path = project_root / creds_path
        
        return creds_path
    
    def load_stock_data_from_cache(self) -> Dict[str, Any]:
        """キャッシュから株式データを読み込み"""
        cache_file = Path("stock_cache.json")
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"キャッシュファイルの読み込みに失敗: {e}")
        
        return {"holdings": [], "watchlist": []}
    
    def save_stock_data_to_cache(self, data: Dict[str, Any]) -> None:
        """株式データをキャッシュに保存"""
        try:
            with open("stock_cache.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.info("株式データをキャッシュに保存しました")
        except Exception as e:
            self.logger.warning(f"キャッシュファイルの保存に失敗: {e}")
    
    # Parameter Store管理メソッド
    
    def get_parameter_store_status(self) -> Dict[str, Any]:
        """Parameter Store統合の状況を取得"""
        if not self._parameter_store_service:
            return {
                "available": False,
                "reason": "Parameter Storeサービスが初期化されていません"
            }
        
        return {
            "available": self._parameter_store_service.is_available,
            "cache_info": self._parameter_store_service.get_cache_info() if self._parameter_store_service.is_available else None,
            "connection_valid": self._parameter_store_service.validate_connection() if self._parameter_store_service.is_available else False
        }
    
    def refresh_config(self, clear_cache: bool = True) -> bool:
        """設定を再読み込み"""
        try:
            if clear_cache and self._parameter_store_service:
                self._parameter_store_service.clear_cache()
            
            # 設定をクリアして再読み込み
            self._config = None
            self._config = self._load_config()
            
            # 検証
            if not self.validate_config(self._config):
                self.logger.error("再読み込みした設定の検証に失敗しました")
                return False
            
            self.logger.info("設定の再読み込みが完了しました")
            return True
            
        except Exception as e:
            self.logger.error(f"設定の再読み込みに失敗: {e}")
            return False
    
    def setup_parameter_store(self, parameters: Dict[str, str], overwrite: bool = False) -> bool:
        """Parameter Storeに初期パラメータを設定"""
        if not self._parameter_store_service or not self._parameter_store_service.is_available:
            self.logger.error("Parameter Storeが利用できません")
            return False
        
        success_count = 0
        total_count = len(parameters)
        
        for key, value in parameters.items():
            try:
                param_path = ParameterStoreConfig.get_parameter_path(key)
                param_type = "SecureString" if ParameterStoreConfig.is_secure_parameter(key) else "String"
                
                success = self._parameter_store_service.put_parameter(
                    parameter_name=param_path,
                    value=value,
                    parameter_type=param_type,
                    description=f"Stock analysis application parameter: {key}",
                    overwrite=overwrite
                )
                
                if success:
                    success_count += 1
                    self.logger.info(f"パラメータ設定成功: {key}")
                else:
                    self.logger.error(f"パラメータ設定失敗: {key}")
                    
            except Exception as e:
                self.logger.error(f"パラメータ設定エラー ({key}): {e}")
        
        self.logger.info(f"Parameter Store設定完了: {success_count}/{total_count}")
        return success_count == total_count
    
    def get_google_credentials_json(self) -> Optional[Dict[str, Any]]:
        """Google認証情報JSONを取得"""
        if not self._parameter_store_service or not self._parameter_store_service.is_available:
            return None
        
        try:
            param_path = ParameterStoreConfig.get_parameter_path("google_credentials")
            credentials_str = self._parameter_store_service.get_parameter(param_path, decrypt=True)
            return json.loads(credentials_str)
        except Exception as e:
            self.logger.error(f"Google認証情報の取得に失敗: {e}")
            return None
    
    def test_all_connections(self) -> Dict[str, bool]:
        """すべての外部サービスへの接続をテスト"""
        results = {}
        
        # Parameter Store接続テスト
        if self._parameter_store_service:
            results["parameter_store"] = self._parameter_store_service.validate_connection()
        else:
            results["parameter_store"] = False
        
        # 設定の取得テスト
        try:
            config = self.get_config()
            results["config_load"] = True
            results["config_valid"] = self.validate_config(config)
        except Exception as e:
            self.logger.error(f"設定の取得/検証に失敗: {e}")
            results["config_load"] = False
            results["config_valid"] = False
        
        return results