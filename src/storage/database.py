
import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path='data/reports.db'):
        # Ensure data directory exists
        data_dir = os.path.join(os.getcwd(), 'data')
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            
        self.db_path = os.path.join(os.getcwd(), db_path)
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        """Initialize the database tables."""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Create anomaly_stocks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS anomaly_stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date DATE NOT NULL,
                market VARCHAR(10) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                name VARCHAR(20),
                price REAL,
                change_pct REAL,
                flow_label VARCHAR(50),
                smart_net REAL,
                retail_net REAL,
                updated_at DATETIME,
                UNIQUE(report_date, symbol)
            )
        ''')

        # Create daily_reports table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date DATE NOT NULL,
                market VARCHAR(10) NOT NULL,
                trigger_type VARCHAR(20) NOT NULL,
                report_content TEXT,
                created_at DATETIME
            )
        ''')

        conn.commit()
        conn.close()

    def upsert_anomaly_stock(self, report_date, market, symbol, name, price, change_pct, flow_label, smart_net, retail_net):
        """Insert or update an anomaly stock record."""
        conn = self.get_connection()
        cursor = conn.cursor()
        updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            cursor.execute('''
                INSERT OR REPLACE INTO anomaly_stocks 
                (report_date, market, symbol, name, price, change_pct, flow_label, smart_net, retail_net, updated_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (report_date, market, symbol, name, price, change_pct, flow_label, smart_net, retail_net, updated_at))
            conn.commit()
        except Exception as e:
            logger.error(f"Error upserting anomaly stock {symbol}: {e}")
        finally:
            conn.close()

    def append_daily_report(self, report_date, market, trigger_type, report_content):
        """Append a new daily report."""
        conn = self.get_connection()
        cursor = conn.cursor()
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            cursor.execute('''
                INSERT INTO daily_reports 
                (report_date, market, trigger_type, report_content, created_at) 
                VALUES (?, ?, ?, ?, ?)
            ''', (report_date, market, trigger_type, report_content, created_at))
            conn.commit()
        except Exception as e:
            logger.error(f"Error appending daily report: {e}")
        finally:
            conn.close()

    def get_reports(self, page=1, per_page=20, market=None, date=None):
        """Get reports with pagination and optional market/date filter."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        offset = (page - 1) * per_page

        try:
            query = 'SELECT * FROM daily_reports'
            params = []
            conditions = []
            
            if market and market != 'All':
                conditions.append('market = ?')
                params.append(market)
            
            if date:
                conditions.append('report_date = ?')
                params.append(date)
                
            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)
                
            query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
            params.extend([per_page, offset])
            
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting reports: {e}")
            return []
        finally:
            conn.close()

    def delete_report(self, report_id):
        """Delete a report by ID."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('DELETE FROM daily_reports WHERE id = ?', (report_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting report {report_id}: {e}")
            return False
        finally:
            conn.close()

db_manager = DatabaseManager()
