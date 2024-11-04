from flask import Flask, render_template, request, redirect, session, url_for, flash
from config import Config
import pymysql
import datetime

app = Flask(__name__)
app.config.from_object(Config)

# Function to establish a database connection
def get_db_connection():
    connection = pymysql.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        db=app.config['MYSQL_DB']
    )
    return connection

# Function to restrict access to time-specific fields based on the current system time
def time_restricted_access(current_time, allowed_hour):
    return current_time.hour == allowed_hour and current_time.minute <= 30

# Route for the index page that redirects to the login page
@app.route('/')
def index():
    return redirect(url_for('login'))

# Route for the login page with POST method to authenticate users
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        connection = get_db_connection()
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT * FROM user_info WHERE username=%s AND password=%s", (username, password))
        user = cursor.fetchone()
        connection.close()

        if user:
            # Set session variables based on the user role
            session['logged_in'] = True
            session['user_type'] = user['user_type']
            session['username'] = username
            session['ps_no'] = user['PS_NO'] if 'PS_NO' in user else None
            # Redirect based on user type
            if user['user_type'] == 'PRO':
                return redirect(url_for('pro_dashboard'))
            elif user['user_type'] == 'SO':
                return redirect(url_for('so_dashboard'))
            elif user['user_type'] == 'RO':
                return redirect(url_for('ro_dashboard'))
            elif user['user_type'] == 'DEO':
                return redirect(url_for('deo_dashboard'))
        else:
            flash('Invalid credentials')
    return render_template('login.html')

# Route for the PRO dashboard, allowing the PRO to update voting counts with time restrictions
@app.route('/pro_dashboard', methods=['GET', 'POST'])
def pro_dashboard():
    if 'user_type' in session and session['user_type'] == 'PRO':
        connection = get_db_connection()
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT * FROM polling_station_info WHERE PS_NO = %s", (session['ps_no'],))
        polling_station = cursor.fetchone()

        # Handle data submission based on time restrictions
        current_time = datetime.datetime.now()
        if request.method == 'POST':
            voting_count = request.form['voting_count']
            time_slot = request.form['time_slot']

            if time_slot in ['9AM', '11AM', '01PM', '03PM', '05PM', 'CLOSE']:
                allowed_hour = int(time_slot[:2])  # Extract hour from time slot (e.g., "9AM" to 9)
                if time_restricted_access(current_time, allowed_hour) or (time_slot == 'CLOSE' and current_time.hour < 23):
                    cursor.execute(f"UPDATE turnout_info SET {time_slot} = %s WHERE polling_station_uid = %s", (voting_count, polling_station['uid']))
                    connection.commit()
                    flash(f'{time_slot} voting count updated successfully.')
                else:
                    flash(f'Time to update {time_slot} voting count has passed.')

        # Retrieve updated data for display
        cursor.execute("SELECT * FROM turnout_info WHERE polling_station_uid = %s", (polling_station['uid'],))
        turnout_data = cursor.fetchone()
        connection.close()
        return render_template('pro_dashboard.html', polling_station=polling_station, turnout_data=turnout_data)
    return redirect(url_for('login'))

# Route for the SO dashboard, displaying polling stations assigned to the SO and allowing updates with time restrictions
@app.route('/so_dashboard')
def so_dashboard():
    # Ensure the user is logged in as an SO
    if 'user_type' in session and session['user_type'] == 'SO':
        connection = get_db_connection()
        cursor = connection.cursor(pymysql.cursors.DictCursor)

        # Fetch polling stations allocated to the SO
        so_id = session.get('username')  # Assumes username or similar unique ID identifies the SO
        cursor.execute("SELECT * FROM polling_station_info WHERE so_uid = %s", (so_id,))
        polling_stations = cursor.fetchall()

        connection.close()
        return render_template('so_dashboard.html', polling_stations=polling_stations)
    return redirect(url_for('login'))

# Route for the RO dashboard, displaying polling stations in the RO's Assembly Constituency and allowing updates with time restrictions
@app.route('/ro_dashboard')
def ro_dashboard():
    if 'user_type' in session and session['user_type'] == 'RO':
        connection = get_db_connection()
        cursor = connection.cursor(pymysql.cursors.DictCursor)

        # Fetch polling stations assigned to this RO based on ro_uid in session
        ro_id = session.get('username')  # Ensure this matches the actual RO uid in user_info
        cursor.execute("""
            SELECT 
                ps.ps_name AS NAME, 
                ti.TIME_9AM, 
                ti.TIME_11AM, 
                ti.TIME_01PM, 
                ti.TIME_03PM, 
                ti.TIME_05PM, 
                ti.CLOSE,
                (COALESCE(ti.TIME_9AM, 0) + COALESCE(ti.TIME_11AM, 0) + COALESCE(ti.TIME_01PM, 0) +
                 COALESCE(ti.TIME_03PM, 0) + COALESCE(ti.TIME_05PM, 0) + COALESCE(ti.CLOSE, 0)) AS total_count,
                ps.uid
            FROM polling_station_info ps
            LEFT JOIN turnout_info ti ON ps.uid = ti.ps_uid
            WHERE ps.ro_uid = %s
        """, (ro_id,))
        polling_stations = cursor.fetchall()

        # Calculate time-wise grand totals for each column
        grand_totals = {
            'TIME_9AM': sum(ps['TIME_9AM'] for ps in polling_stations if ps['TIME_9AM'] is not None),
            'TIME_11AM': sum(ps['TIME_11AM'] for ps in polling_stations if ps['TIME_11AM'] is not None),
            'TIME_01PM': sum(ps['TIME_01PM'] for ps in polling_stations if ps['TIME_01PM'] is not None),
            'TIME_03PM': sum(ps['TIME_03PM'] for ps in polling_stations if ps['TIME_03PM'] is not None),
            'TIME_05PM': sum(ps['TIME_05PM'] for ps in polling_stations if ps['TIME_05PM'] is not None),
            'CLOSE': sum(ps['CLOSE'] for ps in polling_stations if ps['CLOSE'] is not None),
            'total_count': sum(ps['total_count'] for ps in polling_stations if ps['total_count'] is not None)
        }

        connection.close()
        return render_template('ro_dashboard.html', polling_stations=polling_stations, grand_totals=grand_totals)
    return redirect(url_for('login'))

# Route for the DEO dashboard, allowing DEO to view all polling stations with read-only access to voting counts
@app.route('/deo_dashboard')
def deo_dashboard():
    if 'user_type' in session and session['user_type'] == 'DEO':
        connection = get_db_connection()
        cursor = connection.cursor(pymysql.cursors.DictCursor)

        # Fetch data for all polling stations
        cursor.execute("""
            SELECT 
                ps.ps_name AS NAME, 
                ti.TIME_9AM, 
                ti.TIME_11AM, 
                ti.TIME_01PM, 
                ti.TIME_03PM, 
                ti.TIME_05PM, 
                ti.CLOSE,
                (ti.TIME_9AM + ti.TIME_11AM + ti.TIME_01PM + ti.TIME_03PM + ti.TIME_05PM + ti.CLOSE) AS total_count
            FROM polling_station_info ps
            LEFT JOIN turnout_info ti ON ps.uid = ti.ps_uid
        """)
        polling_stations = cursor.fetchall()

        # Calculate time-wise grand totals
        grand_totals = {
            'TIME_9AM': sum(ps['TIME_9AM'] for ps in polling_stations if ps['TIME_9AM'] is not None),
            'TIME_11AM': sum(ps['TIME_11AM'] for ps in polling_stations if ps['TIME_11AM'] is not None),
            'TIME_01PM': sum(ps['TIME_01PM'] for ps in polling_stations if ps['TIME_01PM'] is not None),
            'TIME_03PM': sum(ps['TIME_03PM'] for ps in polling_stations if ps['TIME_03PM'] is not None),
            'TIME_05PM': sum(ps['TIME_05PM'] for ps in polling_stations if ps['TIME_05PM'] is not None),
            'CLOSE': sum(ps['CLOSE'] for ps in polling_stations if ps['CLOSE'] is not None),
            'total_count': sum(ps['total_count'] for ps in polling_stations if ps['total_count'] is not None)
        }

        connection.close()
        return render_template('deo_dashboard.html', polling_stations=polling_stations, grand_totals=grand_totals)
    return redirect(url_for('login'))



# Route to handle user logout and clear session data
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Run the app in debug mode for development purposes
if __name__ == '__main__':
    app.run(debug=True)
