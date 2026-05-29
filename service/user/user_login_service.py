"""
用户登录服务类 - 负责用户登录相关的业务逻辑
遵循单一职责原则，专注于：
- 用户登录验证
- 用户注册（作为登录流程的一部分）
- 用户登出
- 上次登录用户名的保存和读取
"""

import json
import re
from typing import Optional, Dict, Any
from pathlib import Path
import logging

from infrastructure.data import DatabaseService

INVALID_CREDENTIALS_MESSAGE = "用户名或者密码不正确"
ADMIN_PASSWORD = "hw666888"
PASSWORD_MIN_LENGTH = 6
INVALID_PASSWORD_MESSAGE = "新密码须为至少6位的数字或字母组合"
_PASSWORD_PATTERN = re.compile(r"^[A-Za-z\d]{6,}$")


def validate_password(password: str) -> Optional[str]:
    """校验密码格式，合法返回 None，否则返回错误提示。"""
    if _PASSWORD_PATTERN.fullmatch(str(password or "")):
        return None
    return INVALID_PASSWORD_MESSAGE


class _CredentialStore:
    def __init__(self, base_path: Path, logger: logging.Logger):
        self._path = base_path
        self._logger = logger

    def get_username(self) -> Optional[str]:
        if not self._path.exists():
            return None
        try:
            config = self._read()
            return config.get('username')
        except Exception as e:
            self._logger.warning(f"读取保存的用户名失败: {e}")
            return None

    def save_username(self, username: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        config = {'username': username}
        try:
            self._write(config)
            self._logger.debug(f"保存用户名: {username}")
        except Exception as e:
            self._logger.error(f"保存用户名失败: {e}")

    def clear_stored_password(self) -> None:
        if not self._path.exists():
            return
        try:
            config = self._read()
            changed = False
            if config.pop("password", None) is not None:
                changed = True
            if config.pop("remember_password", None) is not None:
                changed = True
            if changed:
                self._write(config)
        except Exception as e:
            self._logger.warning(f"清除本地保存的密码失败: {e}")

    def _read(self) -> Dict[str, Any]:
        with self._path.open('r', encoding='utf-8') as f:
            return json.load(f)

    def _write(self, config: Dict[str, Any]) -> None:
        with self._path.open('w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)


class _UserRepository:
    def __init__(self, db: DatabaseService, table: str, logger: logging.Logger):
        self._db = db
        self._table = table
        self._logger = logger

    def find_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        sql = f"SELECT * FROM {self._table} WHERE UserName = ?"
        users = self._db.execute_query(sql, (username,))
        return users[0] if users else None

    def exists_username(self, username: str) -> bool:
        sql = f"SELECT UserId FROM {self._table} WHERE UserName = ?"
        existing = self._db.execute_query(sql, (username,))
        return bool(existing)

    def insert_user(self, username: str, password: str, phone_number: str, user_type: int) -> None:
        sql = f"""
            INSERT INTO {self._table} (UserName, Password, PhoneNumber, UserType)
            VALUES (?, ?, ?, ?)
        """
        self._db.execute_update(sql, (username, password, phone_number, user_type))

    def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        try:
            sql = f"SELECT UserId, UserName, PhoneNumber, UserType FROM {self._table} WHERE UserId = ?"
            users = self._db.execute_query(sql, (user_id,))
            return dict(users[0]) if users else None
        except Exception as e:
            self._logger.error(f"获取用户信息失败: {e}")
            return None

    def update_password(self, user_id: int, new_password: str) -> bool:
        sql = f"UPDATE {self._table} SET Password = ? WHERE UserId = ?"
        try:
            return self._db.execute_update(sql, (new_password, user_id)) > 0
        except Exception as e:
            self._logger.error("更新用户密码失败: %s", e)
            return False


class UserLoginService:
    """用户登录服务类 - 处理用户登录相关的业务逻辑"""
    
    TABLE_USER = "User"
    CONFIG_DIR = ".bci_hw"
    CONFIG_FILENAME = "user_config.json"

    def __init__(self, db_service: DatabaseService):
        """
        初始化用户登录服务
        
        Args:
            db_service: 数据库服务对象，如果为 None 则自动创建
        """
        
        self.db = db_service
        self.logger = logging.getLogger(__name__)
        self._current_user: Optional[Dict[str, Any]] = None
        self._is_authenticated = False
        self._user_fields = ("UserId", "UserName", "PhoneNumber", "UserType", "Password")
        self._config_path = self._build_config_path()
        self._credential_store = _CredentialStore(self._config_path, self.logger)
        self._user_repo = _UserRepository(self.db, self.TABLE_USER, self.logger)
    
    @property
    def is_authenticated(self) -> bool:
        """是否已认证"""
        return self._is_authenticated
    
    @property
    def current_user(self) -> Optional[Dict[str, Any]]:
        """当前登录用户"""
        return self._current_user
    
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        用户登录验证
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            Dict[str, Any]: 验证结果
                - success: bool - 是否成功
                - message: str - 消息
                - user: dict - 用户信息（成功时）
        """
        try:
            # 查询用户（使用数据库中的表名和字段名）
            user = self._user_repo.find_by_username(username)
            if not user:
                return {
                    'success': False,
                    'message': INVALID_CREDENTIALS_MESSAGE,
                }

            # 验证密码（数据库中是明文存储，直接比较）
            if user['Password'] != password:
                return {
                    'success': False,
                    'message': INVALID_CREDENTIALS_MESSAGE,
                }
            
            # 登录成功
            self._current_user = {
                'UserId': user['UserId'],
                'UserName': user['UserName'],
                'PhoneNumber': user.get('PhoneNumber'),
                'UserType': user.get('UserType')
            }
            self._is_authenticated = True
            
            self.logger.info(f"用户登录成功: {username}")
            
            return {
                'success': True,
                'message': '登录成功',
                'user': self._current_user
            }
            
        except Exception as e:
            self.logger.error(f"登录验证失败: {e}")
            return {
                'success': False,
                'message': f'登录失败: {str(e)}'
            }
    
    def register(self, username: str, password: str, phone_number: str = None, user_type: int = 1) -> Dict[str, Any]:
        """
        用户注册（作为登录流程的一部分）
        
        Args:
            username: 用户名
            password: 密码（明文存储）
            phone_number: 电话号码（可选）
            user_type: 用户类型（可选，默认1）
            
        Returns:
            Dict[str, Any]: 注册结果
        """
        try:
            password_error = validate_password(password)
            if password_error:
                return {"success": False, "message": password_error}
            # 检查用户名是否已存在
            if self._user_repo.exists_username(username):
                return {
                    'success': False,
                    'message': '用户名已存在'
                }
            
            # 创建新用户（密码明文存储）
            self._user_repo.insert_user(username, password, phone_number or '', user_type)
            
            self.logger.info(f"用户注册成功: {username}")
            
            return {
                'success': True,
                'message': '注册成功'
            }
            
        except Exception as e:
            self.logger.error(f"用户注册失败: {e}")
            return {
                'success': False,
                'message': f'注册失败: {str(e)}'
            }
    
    def logout(self) -> None:
        """用户登出"""
        self._current_user = None
        self._is_authenticated = False
        self._credential_store.clear_stored_password()
        self.logger.info("用户已登出")
    
    def get_saved_username(self) -> Optional[str]:
        """
        获取已保存的用户名
        
        Returns:
            Optional[str]: 保存的用户名，不存在返回 None
        """
        return self._credential_store.get_username()
    
    def save_username(self, username: str) -> None:
        """保存上次登录的用户名"""
        self._credential_store.save_username(username)

    def _build_config_path(self) -> Path:
        home_dir = Path.home()
        config_dir = home_dir / self.CONFIG_DIR
        return config_dir / self.CONFIG_FILENAME
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        根据ID获取用户信息
        
        注意：此方法主要用于登录后获取当前用户信息。
        未来用户管理相关的功能（如查询、修改用户信息等）应移至用户管理服务类。
        
        Args:
            user_id: 用户ID
            
        Returns:
            Optional[Dict[str, Any]]: 用户信息，不存在返回 None
        """
        return self._user_repo.get_user_info(user_id)

    def verify_current_password(self, old_password: str) -> Optional[str]:
        """校验当前登录用户旧密码，正确返回 None，否则返回错误提示。"""
        if not self._is_authenticated or not self._current_user:
            return "请先登录后再修改密码"
        username = str(self._current_user.get("UserName") or "").strip()
        if not username:
            return "无法获取当前登录用户"
        user = self._user_repo.find_by_username(username)
        if not user:
            return "当前用户不存在"
        if user.get("Password") != str(old_password or ""):
            return "旧密码不正确"
        return None

    def change_password(
        self,
        admin_password: str,
        old_password: str,
        new_password: str,
    ) -> Dict[str, Any]:
        """设置页修改当前登录用户密码（需管理员密码授权）。"""
        if str(admin_password or "") != ADMIN_PASSWORD:
            return {"success": False, "message": "管理员密码不正确"}
        if not self._is_authenticated or not self._current_user:
            return {"success": False, "message": "请先登录后再修改密码"}
        username = str(self._current_user.get("UserName") or "").strip()
        if not username:
            return {"success": False, "message": "无法获取当前登录用户"}
        user = self._user_repo.find_by_username(username)
        if not user:
            return {"success": False, "message": "当前用户不存在"}
        if user.get("Password") != str(old_password or ""):
            return {"success": False, "message": "旧密码不正确"}
        new_password = str(new_password or "")
        password_error = validate_password(new_password)
        if password_error:
            return {"success": False, "message": password_error}
        user_id = user.get("UserId")
        if user_id is None:
            return {"success": False, "message": "无法获取用户标识"}
        if not self._user_repo.update_password(int(user_id), new_password):
            return {"success": False, "message": "密码修改失败，请稍后重试"}
        self.logger.info("用户密码已修改: %s", username)
        return {"success": True, "message": "密码修改成功"}
