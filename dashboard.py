
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit
from flask_httpauth import HTTPBasicAuth
import discord
from discord.ext import commands
import datetime
import json
import os
import psutil
from pymongo import MongoClient
import asyncio
import threading
import requests
from functools import wraps

# Import bot instance and data functions from main
import main

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')
socketio = SocketIO(app, cors_allowed_origins="*")
auth = HTTPBasicAuth()

# MongoDB connection (reuse from main.py)
mongo_client = main.mongo_client
if mongo_client:
    db = mongo_client["owo_bot"]
    users = db["users"]
    servers = db["servers"]
    inventories = db["inventories"]
    marriages = db["marriages"]
else:
    users = main.users
    servers = main.servers
    inventories = main.inventories
    marriages = main.marriages

def get_bot_stats():
    """Get comprehensive bot statistics"""
    try:
        # Get total users and servers
        bot_guilds = getattr(main.bot, 'guilds', [])
        total_servers = len(bot_guilds) if bot_guilds else 0
        total_users = sum(getattr(guild, 'member_count', 0) for guild in bot_guilds) if bot_guilds else 0
        
        # Get database stats
        try:
            if mongo_client:
                total_registered = users.count_documents({})
                total_balance = sum(user.get('balance', 0) for user in users.find({}))
                total_marriages = marriages.count_documents({"accepted": True})
                active_today = users.count_documents({
                    "last_daily": {"$gte": datetime.datetime.now() - datetime.timedelta(days=1)}
                })
            else:
                total_registered = len(main.users_data)
                total_balance = sum(user.get('balance', 0) for user in main.users_data.values())
                total_marriages = len([m for m in main.marriages_data.values() if m.get('accepted')])
                active_today = 0
        except:
            total_registered = 0
            total_balance = 0
            total_marriages = 0
            active_today = 0
        
        stats = {
            'servers': total_servers,
            'users': total_users,
            'registered_users': total_registered,
            'total_balance': total_balance,
            'marriages': total_marriages,
            'active_today': active_today,
            'commands': len(getattr(main.bot, 'commands', [])),
            'uptime': str(datetime.datetime.now() - main.bot.start_time) if hasattr(main.bot, 'start_time') else "Unknown"
        }
        print(f"Dashboard stats: {stats}")
        return stats
    except Exception as e:
        print(f"Error getting bot stats: {e}")
        import traceback
        traceback.print_exc()
        return {
            'servers': 0,
            'users': 0,
            'registered_users': 0,
            'total_balance': 0,
            'marriages': 0,
            'active_today': 0,
            'commands': 0,
            'uptime': "Unknown"
        }

def get_top_users(limit=10):
    """Get top users by balance"""
    try:
        if mongo_client:
            top_users = list(users.find().sort("balance", -1).limit(limit))
        else:
            top_users = sorted(main.users_data.values(), key=lambda x: x.get('balance', 0), reverse=True)[:limit]
        
        result = []
        for user_data in top_users:
            try:
                user_id = user_data.get('_id')
                user = main.bot.get_user(user_id)
                if user:
                    result.append({
                        'name': user.display_name,
                        'avatar': str(user.display_avatar.url),
                        'balance': user_data.get('balance', 0),
                        'level': user_data.get('level', 1),
                        'rank': user_data.get('rank', 'Newbie')
                    })
            except:
                continue
        return result
    except Exception as e:
        print(f"Error getting top users: {e}")
        return []

def get_recent_activities():
    """Get recent bot activities"""
    try:
        activities = []
        # This would typically come from a logs collection
        # For now, we'll return sample data
        sample_activities = [
            {"action": "User Leveled Up", "user": "Player123", "details": "Reached Level 50", "time": "2 minutes ago"},
            {"action": "Marriage", "user": "User456", "details": "Married User789", "time": "15 minutes ago"},
            {"action": "Big Win", "user": "Gambler321", "details": "Won 50,000 coins in slots", "time": "1 hour ago"},
            {"action": "Rare Hunt", "user": "Hunter999", "details": "Caught a legendary dragon", "time": "2 hours ago"},
            {"action": "Daily Streak", "user": "Dedicated777", "details": "100 day streak milestone", "time": "3 hours ago"}
        ]
        return sample_activities
    except Exception as e:
        print(f"Error getting activities: {e}")
        return []

@app.route('/')
def dashboard():
    """Main dashboard page"""
    try:
        stats = get_bot_stats()
        top_users = get_top_users()
        activities = get_recent_activities()
        
        return render_template('dashboard.html', 
                             stats=stats, 
                             top_users=top_users, 
                             activities=activities)
    except Exception as e:
        print(f"Dashboard route error: {e}")
        return f"Dashboard Error: {e}", 500

@app.route('/api/stats')
def api_stats():
    """API endpoint for real-time stats"""
    return jsonify(get_bot_stats())

@app.route('/api/top-users')
def api_top_users():
    """API endpoint for top users"""
    limit = request.args.get('limit', 10, type=int)
    return jsonify(get_top_users(limit))

@app.route('/users')
def users_page():
    """Users management page"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        if mongo_client:
            total_users = users.count_documents({})
            user_list = list(users.find().skip((page - 1) * per_page).limit(per_page))
        else:
            user_list = list(main.users_data.values()) if hasattr(main, 'users_data') else []
            total_users = len(user_list)
            start = (page - 1) * per_page
            user_list = user_list[start:start + per_page]
        
        # Enrich with Discord data
        enriched_users = []
        for user_data in user_list:
            try:
                user_id = user_data.get('_id')
                if user_id and hasattr(main.bot, 'get_user'):
                    discord_user = main.bot.get_user(user_id)
                    if discord_user:
                        enriched_users.append({
                            'discord_data': {
                                'name': discord_user.display_name,
                                'avatar': str(discord_user.display_avatar.url),
                                'id': discord_user.id
                            },
                            'bot_data': user_data
                        })
                    else:
                        # Add user data even if Discord user not found
                        enriched_users.append({
                            'discord_data': {
                                'name': f'User {user_id}',
                                'avatar': 'https://cdn.discordapp.com/embed/avatars/0.png',
                                'id': user_id
                            },
                            'bot_data': user_data
                        })
            except Exception as user_error:
                print(f"Error processing user {user_data.get('_id', 'unknown')}: {user_error}")
                continue
        
        total_pages = max(1, (total_users + per_page - 1) // per_page) if total_users > 0 else 1
        
        return render_template('users.html', 
                             users=enriched_users,
                             current_page=page,
                             total_pages=total_pages,
                             total_users=total_users)
    except Exception as e:
        print(f"Error in users page: {e}")
        import traceback
        traceback.print_exc()
        # Return a basic HTML page instead of error
        return '''
        <html>
        <body style="background: #2c2c2c; color: white; font-family: Arial;">
        <h1>Users Page</h1>
        <p>Users page is temporarily unavailable. Error: ''' + str(e) + '''</p>
        <a href="/" style="color: #ff4757;">Back to Dashboard</a>
        </body>
        </html>
        ''', 200

@app.route('/servers')
def servers_page():
    """Servers page"""
    try:
        server_list = []
        
        # Check if bot exists and has guilds attribute
        if hasattr(main, 'bot') and hasattr(main.bot, 'guilds'):
            bot_guilds = main.bot.guilds
            
            for guild in bot_guilds:
                try:
                    server_data = {
                        'name': getattr(guild, 'name', 'Unknown Server'),
                        'members': getattr(guild, 'member_count', 0),
                        'owner': 'Unknown',
                        'created': 'Unknown',
                        'icon': None
                    }
                    
                    # Safely get owner info
                    if hasattr(guild, 'owner') and guild.owner:
                        server_data['owner'] = getattr(guild.owner, 'display_name', 'Unknown')
                    
                    # Safely get creation date
                    if hasattr(guild, 'created_at'):
                        server_data['created'] = guild.created_at.strftime('%Y-%m-%d')
                    
                    # Safely get icon
                    if hasattr(guild, 'icon') and guild.icon:
                        server_data['icon'] = str(guild.icon.url)
                    else:
                        server_data['icon'] = 'https://cdn.discordapp.com/embed/avatars/0.png'
                    
                    server_list.append(server_data)
                    
                except Exception as guild_error:
                    print(f"Error processing guild {getattr(guild, 'name', 'Unknown')}: {guild_error}")
                    continue
        
        print(f"Dashboard: Found {len(server_list)} servers")
        return render_template('servers.html', servers=server_list)
        
    except Exception as e:
        print(f"Error in servers page: {e}")
        import traceback
        traceback.print_exc()
        # Return a basic HTML page instead of error
        return '''
        <html>
        <body style="background: #2c2c2c; color: white; font-family: Arial;">
        <h1>Servers Page</h1>
        <p>Servers page is temporarily unavailable. Error: ''' + str(e) + '''</p>
        <a href="/" style="color: #ff4757;">Back to Dashboard</a>
        </body>
        </html>
        ''', 200

def run_dashboard():
    """Run the dashboard in a separate thread"""
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)

@app.route('/test')
def test_route():
    """Test route to verify Flask is working"""
    return "Dashboard is working! This is a test route."

@app.route('/alive')
def keep_alive():
    """Keep-alive endpoint for hosting services"""
    return "Bot is alive!"

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    return "Page not found. Available routes: /, /users, /servers, /test, /api/stats", 404

@app.route('/admin')
@auth.login_required
def admin_panel():
    """Admin control panel"""
    try:
        return render_template('admin.html',
                             uptime=str(datetime.datetime.now() - main.bot.start_time).split('.')[0] if hasattr(main.bot, 'start_time') else "Unknown",
                             cpu_usage=psutil.cpu_percent(),
                             memory_usage=psutil.virtual_memory().percent,
                             admin_secret=os.getenv("ADMIN_SECRET", "secret123"))
    except Exception as e:
        return f"Admin panel error: {e}", 500

@app.route('/restart', methods=['POST'])
def restart_bot():
    """Restart bot (admin only)"""
    if request.form.get('secret') == os.getenv("ADMIN_SECRET", "secret123"):
        # In a real scenario, you'd implement bot restart logic here
        return "Bot restart initiated...", 200
    return "Unauthorized", 403

@app.route('/user/<int:discord_id>')
def user_profile(discord_id):
    """User profile page"""
    try:
        user = main.bot.get_user(discord_id) if hasattr(main.bot, 'get_user') else None
        
        # Get user data from database
        if mongo_client:
            user_data = users.find_one({"_id": discord_id}) or {}
        else:
            user_data = main.users_data.get(discord_id, {}) if hasattr(main, 'users_data') else {}
        
        # Mock warnings for demo (replace with real data)
        warnings = ["Spam (06/01)", "NSFW (06/15)"] if discord_id == 123456789 else []
        
        return render_template('user.html',
                             user=user,
                             user_data=user_data,
                             warnings=warnings,
                             join_date=user.created_at.strftime("%Y-%m-%d") if user else "Unknown")
    except Exception as e:
        return f"User profile error: {e}", 500

@app.route('/api/backup')
def backup_data():
    """Backup bot data (admin only)"""
    try:
        backup = {
            'timestamp': datetime.datetime.now().isoformat(),
            'users': list(users.find()) if mongo_client else main.users_data if hasattr(main, 'users_data') else {},
            'servers': get_bot_stats()
        }
        return jsonify(backup)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected to dashboard')
    emit_system_update()

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected from dashboard')

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return f"Internal server error: {error}", 500

@auth.verify_password
def verify_password(username, password):
    """Verify admin credentials"""
    return username == os.getenv("ADMIN_USER", "admin") and password == os.getenv("ADMIN_PASS", "admin123")

def emit_command_log(user, command):
    """Emit command log to connected clients"""
    socketio.emit('command_log', {
        'user': user,
        'command': command,
        'time': datetime.datetime.now().strftime("%H:%M:%S")
    })

def emit_system_update():
    """Emit system stats update"""
    socketio.emit('system_update', {
        'cpu': psutil.cpu_percent(),
        'memory': psutil.virtual_memory().percent,
        'uptime': str(datetime.datetime.now() - main.bot.start_time).split('.')[0] if hasattr(main.bot, 'start_time') else "Unknown"
    })

def start_dashboard():
    """Start the dashboard server"""
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
    dashboard_thread.start()
    print("Dashboard started on http://0.0.0.0:5000")
