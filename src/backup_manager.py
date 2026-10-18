"""
Backup Manager for Stock Agent Bot
===================================
Handles automatic and manual backups of all important data and code files.

Usage:
    - Automatic: Runs every hour while bot is active
    - Manual: Run `python backup_manager.py` before making code changes
    - Restore: Use /backup command in Telegram or run with --restore flag
"""

import os
import json
import shutil
from datetime import datetime
from pathlib import Path
import zipfile
import argparse

# Base directory
BASE_DIR = Path(__file__).parent

# Backup directory
BACKUP_DIR = BASE_DIR / "backups"

# Data files to backup (JSON files with user data)
DATA_FILES = [
    "my_portfolio.json",
    "israeli_portfolio.json",
    "custom_portfolios.json",
    "dad_portfolio.json",
    "total_log.json",
    "price_alerts.json",
    "triggered_alerts.json",
    "watchlist.json",
    "watchlists.json",
    "seen_news.json",
    "my_notes.json",
    "zacks_cache.json",
    "zacks_custom.json",
    "portfolio_experiment.json",
    "reminders.json",
    "reminder_log.json",
    "savings_goals.json",
    "financial_goals.json",
]

# Code files to backup
CODE_FILES = [
    "telegram_bot.py",
    "telegram_bot_cloud.py",
    "config.py",
    "cli.py",
    "stock_agent.py",
    "ai_advisor.py",
    "news_monitor.py",
    "weekly_news_summary.py",
    "watchlist.py",
    "report_generator.py",
    "scan_bullish.py",
    "scan_medium_term.py",
    "scan_reddit_hype.py",
]

# Folders to backup
CODE_FOLDERS = [
    "analyzers",
    "collectors",
    "primo_agent",
]

# Maximum number of backups to keep (per type)
MAX_HOURLY_BACKUPS = 28  # Keep 7 days of 6-hour backups (4 per day)
MAX_MANUAL_BACKUPS = 20  # Keep 20 pre-change backups (full: data + code)


def ensure_backup_dirs():
    """Create backup directories if they don't exist"""
    (BACKUP_DIR / "hourly").mkdir(parents=True, exist_ok=True)
    (BACKUP_DIR / "manual").mkdir(parents=True, exist_ok=True)
    (BACKUP_DIR / "data_only").mkdir(parents=True, exist_ok=True)


def get_timestamp():
    """Get formatted timestamp for backup naming"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_data_only(backup_type="hourly"):
    """
    Backup only data files (JSON files with user data)
    This is the lightweight backup that runs every hour
    """
    ensure_backup_dirs()
    timestamp = get_timestamp()
    
    if backup_type == "hourly":
        backup_folder = BACKUP_DIR / "hourly" / f"data_{timestamp}"
    else:
        backup_folder = BACKUP_DIR / "data_only" / f"data_{timestamp}"
    
    backup_folder.mkdir(parents=True, exist_ok=True)
    
    backed_up = []
    errors = []
    
    for file_name in DATA_FILES:
        src = BASE_DIR / file_name
        if src.exists():
            try:
                shutil.copy2(src, backup_folder / file_name)
                backed_up.append(file_name)
            except Exception as e:
                errors.append(f"{file_name}: {str(e)}")
    
    # Create backup info file
    info = {
        "timestamp": timestamp,
        "type": "data_only",
        "backup_type": backup_type,
        "files_backed_up": backed_up,
        "errors": errors,
        "created_at": datetime.now().isoformat()
    }
    
    with open(backup_folder / "backup_info.json", "w") as f:
        json.dump(info, f, indent=2)
    
    # Cleanup old backups
    if backup_type == "hourly":
        cleanup_old_backups(BACKUP_DIR / "hourly", MAX_HOURLY_BACKUPS)
    
    return {
        "success": len(errors) == 0,
        "folder": str(backup_folder),
        "files_count": len(backed_up),
        "backed_up": backed_up,
        "errors": errors
    }


def backup_full(reason="manual"):
    """
    Full backup including code and data files
    Creates a ZIP file for easy storage/transfer
    """
    ensure_backup_dirs()
    timestamp = get_timestamp()
    
    backup_folder = BACKUP_DIR / "manual" / f"full_{timestamp}"
    backup_folder.mkdir(parents=True, exist_ok=True)
    
    backed_up = []
    errors = []
    
    # Backup data files
    data_folder = backup_folder / "data"
    data_folder.mkdir(exist_ok=True)
    
    for file_name in DATA_FILES:
        src = BASE_DIR / file_name
        if src.exists():
            try:
                shutil.copy2(src, data_folder / file_name)
                backed_up.append(f"data/{file_name}")
            except Exception as e:
                errors.append(f"data/{file_name}: {str(e)}")
    
    # Backup code files
    code_folder = backup_folder / "code"
    code_folder.mkdir(exist_ok=True)
    
    for file_name in CODE_FILES:
        src = BASE_DIR / file_name
        if src.exists():
            try:
                shutil.copy2(src, code_folder / file_name)
                backed_up.append(f"code/{file_name}")
            except Exception as e:
                errors.append(f"code/{file_name}: {str(e)}")
    
    # Backup code folders
    for folder_name in CODE_FOLDERS:
        src_folder = BASE_DIR / folder_name
        if src_folder.exists():
            try:
                shutil.copytree(src_folder, code_folder / folder_name, 
                              ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                backed_up.append(f"code/{folder_name}/")
            except Exception as e:
                errors.append(f"code/{folder_name}/: {str(e)}")
    
    # Backup .env file (important for API keys)
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            shutil.copy2(env_file, backup_folder / ".env")
            backed_up.append(".env")
        except Exception as e:
            errors.append(f".env: {str(e)}")
    
    # Create backup info file
    info = {
        "timestamp": timestamp,
        "type": "full",
        "reason": reason,
        "files_backed_up": backed_up,
        "errors": errors,
        "created_at": datetime.now().isoformat()
    }
    
    with open(backup_folder / "backup_info.json", "w") as f:
        json.dump(info, f, indent=2)
    
    # Create ZIP archive
    zip_path = BACKUP_DIR / "manual" / f"full_{timestamp}.zip"
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(backup_folder):
                # Skip __pycache__
                dirs[:] = [d for d in dirs if d != '__pycache__']
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(backup_folder)
                    zipf.write(file_path, arcname)
        
        # Remove the folder, keep only ZIP
        shutil.rmtree(backup_folder)
        backed_up.append(f"Created ZIP: {zip_path.name}")
    except Exception as e:
        errors.append(f"ZIP creation: {str(e)}")
    
    # Cleanup old backups
    cleanup_old_backups(BACKUP_DIR / "manual", MAX_MANUAL_BACKUPS, pattern="*.zip")
    
    return {
        "success": len(errors) == 0,
        "zip_path": str(zip_path),
        "files_count": len(backed_up),
        "backed_up": backed_up,
        "errors": errors
    }


def cleanup_old_backups(backup_path, max_keep, pattern=None):
    """Remove old backups, keeping only the most recent ones"""
    try:
        if pattern:
            # For ZIP files
            backups = sorted(backup_path.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)
        else:
            # For folders
            backups = sorted([d for d in backup_path.iterdir() if d.is_dir()], 
                           key=lambda x: x.stat().st_mtime, reverse=True)
        
        # Remove old backups
        for old_backup in backups[max_keep:]:
            if old_backup.is_dir():
                shutil.rmtree(old_backup)
            else:
                old_backup.unlink()
    except Exception as e:
        print(f"Warning: Cleanup failed: {e}")


def list_backups():
    """List all available backups"""
    ensure_backup_dirs()
    
    backups = {
        "hourly": [],
        "manual": [],
        "data_only": []
    }
    
    # List hourly backups
    hourly_dir = BACKUP_DIR / "hourly"
    for folder in sorted(hourly_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if folder.is_dir():
            info_file = folder / "backup_info.json"
            if info_file.exists():
                with open(info_file) as f:
                    info = json.load(f)
                backups["hourly"].append({
                    "name": folder.name,
                    "path": str(folder),
                    "created": info.get("created_at", "Unknown"),
                    "files": len(info.get("files_backed_up", []))
                })
    
    # List manual backups (ZIP files)
    manual_dir = BACKUP_DIR / "manual"
    for zip_file in sorted(manual_dir.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
        backups["manual"].append({
            "name": zip_file.name,
            "path": str(zip_file),
            "created": datetime.fromtimestamp(zip_file.stat().st_mtime).isoformat(),
            "size_mb": round(zip_file.stat().st_size / (1024 * 1024), 2)
        })
    
    return backups


def restore_backup(backup_path, restore_data=True, restore_code=False):
    """
    Restore from a backup
    
    Args:
        backup_path: Path to backup folder or ZIP file
        restore_data: Whether to restore data files (default: True)
        restore_code: Whether to restore code files (default: False - be careful!)
    """
    backup_path = Path(backup_path)
    
    if not backup_path.exists():
        return {"success": False, "error": f"Backup not found: {backup_path}"}
    
    restored = []
    errors = []
    
    # If it's a ZIP file, extract first
    temp_folder = None
    if backup_path.suffix == ".zip":
        temp_folder = BACKUP_DIR / "temp_restore"
        if temp_folder.exists():
            shutil.rmtree(temp_folder)
        temp_folder.mkdir()
        
        with zipfile.ZipFile(backup_path, 'r') as zipf:
            zipf.extractall(temp_folder)
        
        backup_path = temp_folder
    
    # Restore data files
    if restore_data:
        data_folder = backup_path / "data" if (backup_path / "data").exists() else backup_path
        
        for file_name in DATA_FILES:
            src = data_folder / file_name
            if src.exists():
                try:
                    dest = BASE_DIR / file_name
                    shutil.copy2(src, dest)
                    restored.append(file_name)
                except Exception as e:
                    errors.append(f"{file_name}: {str(e)}")
    
    # Restore code files (dangerous - requires explicit confirmation)
    if restore_code:
        code_folder = backup_path / "code"
        if code_folder.exists():
            for file_name in CODE_FILES:
                src = code_folder / file_name
                if src.exists():
                    try:
                        dest = BASE_DIR / file_name
                        shutil.copy2(src, dest)
                        restored.append(f"code: {file_name}")
                    except Exception as e:
                        errors.append(f"code/{file_name}: {str(e)}")
            
            # Restore code folders
            for folder_name in CODE_FOLDERS:
                src_folder = code_folder / folder_name
                if src_folder.exists():
                    try:
                        dest_folder = BASE_DIR / folder_name
                        if dest_folder.exists():
                            shutil.rmtree(dest_folder)
                        shutil.copytree(src_folder, dest_folder)
                        restored.append(f"code: {folder_name}/")
                    except Exception as e:
                        errors.append(f"code/{folder_name}/: {str(e)}")
    
    # Cleanup temp folder
    if temp_folder and temp_folder.exists():
        shutil.rmtree(temp_folder)
    
    return {
        "success": len(errors) == 0,
        "restored": restored,
        "errors": errors
    }


def get_backup_summary():
    """Get a summary of backup status for display"""
    backups = list_backups()
    
    # Get latest hourly
    latest_hourly = backups["hourly"][0] if backups["hourly"] else None
    
    # Get latest manual
    latest_manual = backups["manual"][0] if backups["manual"] else None
    
    # Calculate total backup size
    total_size = 0
    for b in backups["manual"]:
        total_size += b.get("size_mb", 0)
    
    # Count hourly backups folder size
    hourly_dir = BACKUP_DIR / "hourly"
    if hourly_dir.exists():
        for folder in hourly_dir.iterdir():
            if folder.is_dir():
                for file in folder.rglob("*"):
                    if file.is_file():
                        total_size += file.stat().st_size / (1024 * 1024)
    
    return {
        "hourly_count": len(backups["hourly"]),
        "manual_count": len(backups["manual"]),
        "latest_hourly": latest_hourly,
        "latest_manual": latest_manual,
        "total_size_mb": round(total_size, 2)
    }


# CLI Interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backup Manager for Stock Agent Bot")
    parser.add_argument("--full", action="store_true", help="Create full backup (data + code)")
    parser.add_argument("--data", action="store_true", help="Create data-only backup")
    parser.add_argument("--list", action="store_true", help="List all backups")
    parser.add_argument("--restore", type=str, help="Restore from backup path")
    parser.add_argument("--restore-code", action="store_true", help="Also restore code files (use with --restore)")
    parser.add_argument("--reason", type=str, default="manual", help="Reason for backup")
    
    args = parser.parse_args()
    
    if args.list:
        print("\n📦 BACKUP STATUS")
        print("=" * 50)
        summary = get_backup_summary()
        print(f"📁 Hourly backups: {summary['hourly_count']}")
        print(f"📁 Manual backups: {summary['manual_count']}")
        print(f"💾 Total size: {summary['total_size_mb']} MB")
        
        if summary["latest_hourly"]:
            print(f"\n⏰ Latest hourly: {summary['latest_hourly']['name']}")
            print(f"   Created: {summary['latest_hourly']['created']}")
        
        if summary["latest_manual"]:
            print(f"\n🔧 Latest manual: {summary['latest_manual']['name']}")
            print(f"   Created: {summary['latest_manual']['created']}")
            print(f"   Size: {summary['latest_manual']['size_mb']} MB")
        
        backups = list_backups()
        
        if backups["manual"]:
            print("\n📋 Manual backups (most recent first):")
            for b in backups["manual"][:10]:
                print(f"   - {b['name']} ({b['size_mb']} MB)")
        
        if backups["hourly"]:
            print("\n📋 Hourly backups (most recent first):")
            for b in backups["hourly"][:10]:
                print(f"   - {b['name']} ({b['files']} files)")
    
    elif args.restore:
        print(f"\n🔄 RESTORING FROM: {args.restore}")
        result = restore_backup(args.restore, restore_data=True, restore_code=args.restore_code)
        
        if result["success"]:
            print("✅ Restore completed successfully!")
            print(f"📁 Restored {len(result['restored'])} items:")
            for item in result["restored"]:
                print(f"   - {item}")
        else:
            print("❌ Restore had errors:")
            for err in result["errors"]:
                print(f"   - {err}")
    
    elif args.data:
        print("\n💾 Creating data-only backup...")
        result = backup_data_only("manual")
        
        if result["success"]:
            print(f"✅ Data backup created: {result['folder']}")
            print(f"📁 Backed up {result['files_count']} files")
        else:
            print("❌ Backup had errors:")
            for err in result["errors"]:
                print(f"   - {err}")
    
    else:  # Default: full backup
        reason = args.reason
        print(f"\n📦 Creating FULL backup (reason: {reason})...")
        result = backup_full(reason)
        
        if result["success"]:
            print(f"✅ Full backup created: {result['zip_path']}")
            print(f"📁 Backed up {result['files_count']} items")
        else:
            print("❌ Backup had errors:")
            for err in result["errors"]:
                print(f"   - {err}")

    print()
