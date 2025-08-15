"""
AWS Parameter Store統合サービス
設定値の安全な読み込み、キャッシュ、エラーハンドリングを提供
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import threading

try:
    import boto3
    from botocore.exceptions import ClientError, BotoCoreError, NoCredentialsError
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False

from src.utils.validators import ValidationError

logger = logging.getLogger(__name__)


@dataclass
class ParameterCacheEntry:
    """Parameter Storeキャッシュエントリ"""
    value: str
    last_updated: datetime
    ttl_seconds: int = 300  # 5分のデフォルトTTL
    is_secure: bool = False
    
    @property
    def is_expired(self) -> bool:
        """キャッシュが期限切れかチェック"""
        return datetime.now() > self.last_updated + timedelta(seconds=self.ttl_seconds)


class ParameterStoreService:
    """Parameter Store統合サービス"""
    
    def __init__(self, region_name: str = "ap-northeast-1"):
        """
        Args:
            region_name: AWS リージョン名
        """
        self.region_name = region_name
        self.logger = logging.getLogger(__name__)
        self._client = None
        self._cache: Dict[str, ParameterCacheEntry] = {}
        self._cache_lock = threading.Lock()
        
        # AWS可用性チェック
        if not AWS_AVAILABLE:
            self.logger.warning("boto3がインストールされていません。AWS機能は利用できません。")
            return
        
        try:
            self._initialize_client()
        except Exception as e:
            self.logger.error(f"Parameter Store client初期化に失敗: {e}")
    
    def _initialize_client(self):
        """SSM clientを初期化"""
        if not AWS_AVAILABLE:
            raise RuntimeError("boto3が利用できません")
        
        try:
            # 認証情報の確認
            session = boto3.Session()
            credentials = session.get_credentials()
            
            if credentials is None:
                raise NoCredentialsError()
            
            self._client = boto3.client('ssm', region_name=self.region_name)
            
            # 接続テスト
            self._client.describe_parameters(MaxResults=1)
            
            self.logger.info(f"Parameter Store client初期化完了 (region: {self.region_name})")
            
        except NoCredentialsError:
            self.logger.error(
                "AWS認証情報が設定されていません。"
                "AWS CLI設定、環境変数、またはIAMロールを確認してください。"
            )
            raise
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'UnauthorizedOperation':
                self.logger.error("Parameter Storeへのアクセス権限がありません")
            else:
                self.logger.error(f"Parameter Store接続エラー: {e}")
            raise
        except Exception as e:
            self.logger.error(f"予期しないエラー: {e}")
            raise
    
    @property
    def is_available(self) -> bool:
        """Parameter Storeが利用可能かチェック"""
        return AWS_AVAILABLE and self._client is not None
    
    def get_parameter(self, 
                     parameter_name: str, 
                     decrypt: bool = False,
                     use_cache: bool = True,
                     cache_ttl: int = 300) -> str:
        """
        Parameter Storeからパラメータを取得
        
        Args:
            parameter_name: パラメータ名
            decrypt: 暗号化されたパラメータを復号化するか
            use_cache: キャッシュを使用するか
            cache_ttl: キャッシュTTL（秒）
            
        Returns:
            str: パラメータ値
            
        Raises:
            RuntimeError: Parameter Storeが利用できない場合
            ValueError: パラメータが見つからない場合
            ClientError: AWS API エラー
        """
        if not self.is_available:
            raise RuntimeError(
                "Parameter Storeが利用できません。"
                "AWS設定と認証情報を確認してください。"
            )
        
        # キャッシュチェック
        if use_cache:
            cached_value = self._get_from_cache(parameter_name)
            if cached_value is not None:
                self.logger.debug(f"キャッシュからパラメータを取得: {parameter_name}")
                return cached_value
        
        try:
            self.logger.debug(f"Parameter Storeからパラメータを取得: {parameter_name}")
            
            response = self._client.get_parameter(
                Name=parameter_name,
                WithDecryption=decrypt
            )
            
            value = response['Parameter']['Value']
            
            # キャッシュに保存
            if use_cache:
                self._save_to_cache(parameter_name, value, cache_ttl, decrypt)
            
            return value
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            
            if error_code == 'ParameterNotFound':
                raise ValueError(f"パラメータが見つかりません: {parameter_name}")
            elif error_code == 'AccessDeniedException':
                raise PermissionError(f"パラメータへのアクセスが拒否されました: {parameter_name}")
            else:
                self.logger.error(f"Parameter Store API エラー: {e}")
                raise
        
        except Exception as e:
            self.logger.error(f"パラメータ取得中に予期しないエラー: {e}")
            raise
    
    def get_parameters_by_path(self, 
                              path: str, 
                              recursive: bool = True,
                              decrypt: bool = False,
                              use_cache: bool = True) -> Dict[str, str]:
        """
        パスを指定して複数のパラメータを取得
        
        Args:
            path: パラメータパス（例: /stock-analysis/）
            recursive: 再帰的に取得するか
            decrypt: 暗号化されたパラメータを復号化するか
            use_cache: キャッシュを使用するか
            
        Returns:
            Dict[str, str]: パラメータ名と値の辞書
        """
        if not self.is_available:
            raise RuntimeError("Parameter Storeが利用できません")
        
        parameters = {}
        next_token = None
        
        try:
            while True:
                kwargs = {
                    'Path': path,
                    'Recursive': recursive,
                    'WithDecryption': decrypt,
                    'MaxResults': 10
                }
                
                if next_token:
                    kwargs['NextToken'] = next_token
                
                response = self._client.get_parameters_by_path(**kwargs)
                
                for param in response.get('Parameters', []):
                    param_name = param['Name']
                    param_value = param['Value']
                    parameters[param_name] = param_value
                    
                    # キャッシュに保存
                    if use_cache:
                        self._save_to_cache(param_name, param_value, 300, decrypt)
                
                next_token = response.get('NextToken')
                if not next_token:
                    break
            
            self.logger.info(f"パス '{path}' から {len(parameters)} 個のパラメータを取得")
            return parameters
            
        except ClientError as e:
            self.logger.error(f"パスによるパラメータ取得エラー: {e}")
            raise
    
    def put_parameter(self, 
                     parameter_name: str,
                     value: str,
                     parameter_type: str = "String",
                     description: str = "",
                     overwrite: bool = True) -> bool:
        """
        Parameter Storeにパラメータを保存
        
        Args:
            parameter_name: パラメータ名
            value: パラメータ値
            parameter_type: パラメータタイプ（String, StringList, SecureString）
            description: 説明
            overwrite: 既存パラメータを上書きするか
            
        Returns:
            bool: 成功したかどうか
        """
        if not self.is_available:
            raise RuntimeError("Parameter Storeが利用できません")
        
        try:
            kwargs = {
                'Name': parameter_name,
                'Value': value,
                'Type': parameter_type,
                'Overwrite': overwrite
            }
            
            if description:
                kwargs['Description'] = description
            
            self._client.put_parameter(**kwargs)
            
            # キャッシュを無効化
            self._invalidate_cache(parameter_name)
            
            self.logger.info(f"パラメータを保存: {parameter_name}")
            return True
            
        except ClientError as e:
            self.logger.error(f"パラメータ保存エラー: {e}")
            return False
    
    def _get_from_cache(self, parameter_name: str) -> Optional[str]:
        """キャッシュからパラメータを取得"""
        with self._cache_lock:
            entry = self._cache.get(parameter_name)
            if entry and not entry.is_expired:
                return entry.value
            elif entry and entry.is_expired:
                # 期限切れキャッシュを削除
                del self._cache[parameter_name]
        return None
    
    def _save_to_cache(self, 
                      parameter_name: str, 
                      value: str, 
                      ttl_seconds: int,
                      is_secure: bool = False):
        """キャッシュにパラメータを保存"""
        with self._cache_lock:
            self._cache[parameter_name] = ParameterCacheEntry(
                value=value,
                last_updated=datetime.now(),
                ttl_seconds=ttl_seconds,
                is_secure=is_secure
            )
    
    def _invalidate_cache(self, parameter_name: str = None):
        """キャッシュを無効化"""
        with self._cache_lock:
            if parameter_name:
                self._cache.pop(parameter_name, None)
            else:
                self._cache.clear()
    
    def clear_cache(self):
        """すべてのキャッシュをクリア"""
        self._invalidate_cache()
        self.logger.info("Parameter Storeキャッシュをクリアしました")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """キャッシュ情報を取得"""
        with self._cache_lock:
            cache_info = {
                "total_entries": len(self._cache),
                "secure_entries": sum(1 for entry in self._cache.values() if entry.is_secure),
                "expired_entries": sum(1 for entry in self._cache.values() if entry.is_expired),
                "entries": []
            }
            
            for name, entry in self._cache.items():
                cache_info["entries"].append({
                    "name": name,
                    "last_updated": entry.last_updated.isoformat(),
                    "ttl_seconds": entry.ttl_seconds,
                    "is_secure": entry.is_secure,
                    "is_expired": entry.is_expired
                })
        
        return cache_info
    
    def validate_connection(self) -> bool:
        """Parameter Storeへの接続を検証"""
        if not self.is_available:
            return False
        
        try:
            # 軽量な接続テスト
            self._client.describe_parameters(MaxResults=1)
            return True
        except Exception as e:
            self.logger.error(f"Parameter Store接続検証に失敗: {e}")
            return False


class ParameterStoreConfig:
    """Parameter Store設定の管理クラス"""
    
    # 標準パラメータパス
    BASE_PATH = "/stock-analysis"
    PARAMETER_PATHS = {
        "google_sheets_id": f"{BASE_PATH}/google-sheets-id",
        "google_credentials": f"{BASE_PATH}/google-credentials",
        "gemini_api_key": f"{BASE_PATH}/gemini-api-key",
        "slack_webhook": f"{BASE_PATH}/slack-webhook",
        "slack_channel": f"{BASE_PATH}/slack-channel",
        "log_level": f"{BASE_PATH}/log-level",
        "analysis_schedule": f"{BASE_PATH}/analysis-schedule"
    }
    
    # セキュアパラメータ（暗号化が必要）
    SECURE_PARAMETERS = {
        "google_credentials",
        "gemini_api_key", 
        "slack_webhook"
    }
    
    @classmethod
    def get_parameter_path(cls, key: str) -> str:
        """パラメータキーからフルパスを取得"""
        if key in cls.PARAMETER_PATHS:
            return cls.PARAMETER_PATHS[key]
        else:
            return f"{cls.BASE_PATH}/{key}"
    
    @classmethod
    def is_secure_parameter(cls, key: str) -> bool:
        """パラメータが暗号化対象かチェック"""
        return key in cls.SECURE_PARAMETERS
    
    @classmethod
    def get_all_parameter_paths(cls) -> List[str]:
        """すべてのパラメータパスを取得"""
        return list(cls.PARAMETER_PATHS.values())
    
    @classmethod
    def validate_parameter_structure(cls, parameters: Dict[str, str]) -> List[str]:
        """パラメータ構造の妥当性を検証"""
        errors = []
        
        # 必須パラメータのチェック
        required_params = {
            "google_sheets_id",
            "gemini_api_key", 
            "slack_webhook"
        }
        
        missing_params = required_params - set(parameters.keys())
        if missing_params:
            errors.append(f"必須パラメータが不足しています: {', '.join(missing_params)}")
        
        # パラメータ値の基本検証
        for key, value in parameters.items():
            if not value or not value.strip():
                errors.append(f"パラメータ '{key}' が空です")
            
            # 長さチェック
            if len(value) > 8192:  # Parameter Storeの制限
                errors.append(f"パラメータ '{key}' が長すぎます（8192文字以下）")
        
        return errors