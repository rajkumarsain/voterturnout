from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
from config import Config
import pymysql
from datetime import datetime, timedelta

app = Flask(__name__)
app.config.from_object(Config)

app.secret_key = 'your_secret_key'  # Necessary for session handling

# Hardcoded admin credentials
ADMIN_USERNAME = "admin_doitc"
ADMIN_PASSWORD = "doitc@3721"

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
    return current_time.hour == allowed_hour and current_time.minute <= 50

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

#ROUTE FOR PRO DASHBOARD
from datetime import datetime, timedelta  # Import the classes directly from datetime module

@app.route('/pro_dashboard', methods=['GET', 'POST'])
def pro_dashboard():
    if 'user_type' in session and session['user_type'] == 'PRO':
        connection = get_db_connection()
        cursor = connection.cursor(pymysql.cursors.DictCursor)

        # Retrieve the PRO's `uid`
        cursor.execute("SELECT uid FROM user_info WHERE username = %s", (session['username'],))
        pro_user = cursor.fetchone()

        if pro_user is None:
            flash("User not found.")
            connection.close()
            return redirect(url_for('login'))

        pro_uid = pro_user['uid']

        # Retrieve the associated polling station for this PRO user
        cursor.execute("""
            SELECT ps.ps_no, ps.ps_name AS NAME, ps.ps_uid,
                   ai.state_code, ai.deo_district_code AS district_code, ai.assembly_code
            FROM polling_station_info ps
            JOIN assembly_info ai ON ps.ac_no = ai.assembly_code
            WHERE ps.pro_uid = %s
        """, (pro_uid,))
        
        polling_station = cursor.fetchone()

        if polling_station is None:
            flash("No polling station found for this PRO user.")
            connection.close()
            return redirect(url_for('login'))

        # Determine editable time slots based on `time_slots` table
        current_time = datetime.now()  # Correct usage here
        editable_slots = {}
        
        # Query all time slots from the database
        cursor.execute("SELECT slot_name, slot_hour, slot_minute, edit_interval FROM time_slots")
        time_slots_data = cursor.fetchall()

        for slot in time_slots_data:
            # Properly reference datetime to create time slots
            slot_time = datetime(current_time.year, current_time.month, current_time.day,
                                 slot['slot_hour'], slot['slot_minute'])
            end_time = slot_time + timedelta(minutes=slot['edit_interval'])
            editable_slots[slot['slot_name']] = (slot_time <= current_time <= end_time)

        # Handle form submission for updating voting count
        if request.method == 'POST':
            # Retrieve time slot and voting count values
            time_slot = request.form.get('time_slot')
            voting_count_key = f"voting_count_{time_slot}"  # Example: voting_count_TIME_9AM
            voting_count = request.form.get(voting_count_key)

            # Debugging output to verify data received from the form
            print("Received Time Slot:", time_slot)
            print("Voting Count from form:", voting_count)

            if voting_count and time_slot in editable_slots:
                try:
                    # Convert voting_count to integer
                    voting_count = int(voting_count)
                    print("Converted Voting Count:", voting_count)

                    # Execute update query for specific time slot
                    update_query = f"UPDATE turnout_info SET {time_slot} = %s WHERE ps_uid = %s"
                    cursor.execute(update_query, (voting_count, polling_station['ps_uid']))
                    connection.commit()
                    flash(f'{time_slot} voting count updated successfully to {voting_count}.')

                    # Verify the update
                    cursor.execute("SELECT * FROM turnout_info WHERE ps_uid = %s", (polling_station['ps_uid'],))
                    updated_data = cursor.fetchone()
                    print("Updated turnout data in database:", updated_data)

                except ValueError:
                    flash("Invalid voting count entered. Please enter a valid number.")
            else:
                flash("Invalid form submission or time slot has passed.")

        # Retrieve updated turnout data for display on the page
        cursor.execute("SELECT * FROM turnout_info WHERE ps_uid = %s", (polling_station['ps_uid'],))
        turnout_data = cursor.fetchone()
        print("Turnout Data Displayed to User:", turnout_data)

        connection.close()

        return render_template(
            'pro_dashboard.html', 
            polling_station=polling_station, 
            turnout_data=turnout_data,
            editable_slots=editable_slots
        )
    return redirect(url_for('login'))


# Route for the SO dashboard, displaying polling stations assigned to the SO and allowing updates with time restrictions
from datetime import datetime, timedelta
@app.route('/so_dashboard', methods=['GET', 'POST'])
def so_dashboard():
    if 'user_type' in session and session['user_type'] == 'SO':
        connection = get_db_connection()
        cursor = connection.cursor(pymysql.cursors.DictCursor)

        so_id = session.get('username')
        cursor.execute("""
            SELECT ps.ps_no, ps.ps_name AS NAME, ps.ps_uid,
                   ti.TIME_9AM, ti.TIME_11AM, ti.TIME_01PM, ti.TIME_03PM, ti.TIME_05PM, ti.CLOSE
            FROM polling_station_info ps
            LEFT JOIN turnout_info ti ON ps.ps_uid = ti.ps_uid
            JOIN user_info u ON ps.so_uid = u.uid
            WHERE u.username = %s
        """, (so_id,))
        
        polling_stations = cursor.fetchall()

        # Fetch time slots from database for determining editable slots
        cursor.execute("SELECT slot_name, slot_hour, slot_minute, edit_interval FROM time_slots")
        time_slots_data = cursor.fetchall()

        current_time = datetime.now()
        editable_slot = None

        # Determine the single editable slot based on the current time
        for slot in time_slots_data:
            slot_time = datetime(current_time.year, current_time.month, current_time.day,
                                 slot['slot_hour'], slot['slot_minute'])
            end_time = slot_time + timedelta(minutes=slot['edit_interval'])
            if slot_time <= current_time <= end_time:
                editable_slot = slot['slot_name']
                break  # Only one slot should be editable at a time

        # Handle form submission for updating voting count
        if request.method == 'POST' and editable_slot:
            ps_uid = request.form.get('ps_uid')
            voting_count = request.form.get(f'voting_count_{ps_uid}_{editable_slot}')

            if voting_count:
                try:
                    voting_count = int(voting_count)
                    update_query = f"UPDATE turnout_info SET {editable_slot} = %s WHERE ps_uid = %s"
                    cursor.execute(update_query, (voting_count, ps_uid))
                    connection.commit()
                    flash(f'Voting count for {editable_slot} updated successfully for Polling Station {ps_uid}.')

                except ValueError:
                    flash("Invalid voting count entered. Please enter a valid number.")

        # Re-fetch polling stations to display updated data
        cursor.execute("""
            SELECT ps.ps_no, ps.ps_name AS NAME, ps.ps_uid,
                   ti.TIME_9AM, ti.TIME_11AM, ti.TIME_01PM, ti.TIME_03PM, ti.TIME_05PM, ti.CLOSE
            FROM polling_station_info ps
            LEFT JOIN turnout_info ti ON ps.ps_uid = ti.ps_uid
            JOIN user_info u ON ps.so_uid = u.uid
            WHERE u.username = %s
        """, (so_id,))
        polling_stations = cursor.fetchall()

        # Calculate grand totals
        grand_totals = {
            'TIME_9AM': sum(ps['TIME_9AM'] for ps in polling_stations if ps['TIME_9AM'] is not None),
            'TIME_11AM': sum(ps['TIME_11AM'] for ps in polling_stations if ps['TIME_11AM'] is not None),
            'TIME_01PM': sum(ps['TIME_01PM'] for ps in polling_stations if ps['TIME_01PM'] is not None),
            'TIME_03PM': sum(ps['TIME_03PM'] for ps in polling_stations if ps['TIME_03PM'] is not None),
            'TIME_05PM': sum(ps['TIME_05PM'] for ps in polling_stations if ps['TIME_05PM'] is not None),
            'CLOSE': sum(ps['CLOSE'] for ps in polling_stations if ps['CLOSE'] is not None),
        }

        connection.close()
        return render_template(
            'so_dashboard.html', 
            polling_stations=polling_stations, 
            grand_totals=grand_totals,
            editable_slots={editable_slot: True} if editable_slot else {}
        )
    return redirect(url_for('login'))

# Route for the RO dashboard, displaying polling stations in the RO's Assembly Constituency and allowing updates with time restrictions
@app.route('/ro_dashboard')
def ro_dashboard():
    if 'user_type' in session and session['user_type'] == 'RO':
        connection = get_db_connection()
        cursor = connection.cursor(pymysql.cursors.DictCursor)

        # Retrieve ro_id based on username in session
        username = session.get('username')
        cursor.execute("SELECT uid FROM user_info WHERE username = %s", (username,))
        ro_data = cursor.fetchone()
        
        if not ro_data:
            flash("RO ID not found for the current user.")
            return redirect(url_for('login'))
        
        ro_id = ro_data['uid']

        # Fetch polling stations and turnout data
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
                ps.ps_uid
            FROM polling_station_info ps
            LEFT JOIN turnout_info ti ON ps.ps_uid = ti.ps_uid
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
            LEFT JOIN turnout_info ti ON ps.ps_uid = ti.ps_uid
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


@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Check if the entered credentials match the hardcoded credentials
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid username or password", "danger")
    return render_template('admin_login.html')

@app.route('/admin_dashboard')
def admin_dashboard():
    # Ensure only logged-in users can access the dashboard
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    return render_template('admin_dashboard.html')

@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash("You have been logged out", "success")
    return redirect(url_for('admin_login'))

#ROUTE TO SHOW MANAGE POLLING STATION INFORMATION
@app.route('/manage_polling_station', methods=['GET', 'POST'])
def manage_polling_station():
    connection = get_db_connection()
    cursor = connection.cursor(pymysql.cursors.DictCursor)
    
    # Fetch users by role for dropdowns, including mobile numbers
    cursor.execute("SELECT uid, name, mobile_number FROM user_info WHERE user_type = 'DEO'")
    deo_users = cursor.fetchall()
    
    cursor.execute("SELECT uid, name, mobile_number FROM user_info WHERE user_type = 'RO'")
    ro_users = cursor.fetchall()
    
    cursor.execute("SELECT uid, name, mobile_number FROM user_info WHERE user_type = 'SO'")
    so_users = cursor.fetchall()
    
    cursor.execute("SELECT uid, name, mobile_number FROM user_info WHERE user_type = 'PRO'")
    pro_users = cursor.fetchall()

    # Fetch all polling stations
    cursor.execute("SELECT * FROM polling_station_info")
    polling_stations = cursor.fetchall()

    connection.close()
    return render_template(
        'manage_polling_station.html', 
        polling_stations=polling_stations, 
        deo_users=deo_users,
        ro_users=ro_users,
        so_users=so_users,
        pro_users=pro_users
    )


@app.route('/update_polling_station/<int:ps_uid>', methods=['POST'])
def update_polling_station(ps_uid):
    connection = get_db_connection()
    cursor = connection.cursor()
    
    ps_no = request.form['ps_no']
    ps_name = request.form['ps_name']
    pc_no = request.form['pc_no']
    ac_no = request.form['ac_no']
    deo_uid = request.form['deo_uid']
    ro_uid = request.form['ro_uid']
    so_uid = request.form['so_uid']
    pro_uid = request.form['pro_uid']
    total_voter = request.form['total_voter']
    
    # Update polling station details
    cursor.execute("""
        UPDATE polling_station_info 
        SET ps_no = %s, ps_name = %s, pc_no = %s, ac_no = %s, deo_uid = %s, ro_uid = %s, so_uid = %s, pro_uid = %s, total_voter = %s
        WHERE ps_uid = %s
    """, (ps_no, ps_name, pc_no, ac_no, deo_uid, ro_uid, so_uid, pro_uid, total_voter, ps_uid))
    connection.commit()
    connection.close()
    
    flash("Polling station updated successfully.", "success")
    return redirect(url_for('manage_polling_station'))

#to delete polling station from polling_station_info table
@app.route('/delete_polling_station/<int:ps_uid>', methods=['POST'])
def delete_polling_station(ps_uid):
    connection = get_db_connection()
    cursor = connection.cursor()
    
    # Delete polling station
    cursor.execute("DELETE FROM polling_station_info WHERE ps_uid = %s", (ps_uid,))
    connection.commit()
    connection.close()
    
    flash("Polling station deleted successfully.", "danger")
    return redirect(url_for('manage_polling_station'))

@app.route('/manage_time_slots', methods=['GET', 'POST'])
def manage_time_slots():
    connection = get_db_connection()
    cursor = connection.cursor(pymysql.cursors.DictCursor)
    
    # Handle adding a new time slot
    if request.method == 'POST' and 'add_time_slot' in request.form:
        slot_name = request.form['slot_name']
        slot_hour = request.form['slot_hour']
        slot_minute = request.form['slot_minute']
        edit_interval = request.form['edit_interval']
        
        # Check if the time slot already exists
        cursor.execute("SELECT * FROM time_slots WHERE slot_name = %s", (slot_name,))
        existing_slot = cursor.fetchone()
        
        if existing_slot:
            flash("Time slot with this name already exists.", "danger")
        else:
            # Insert the new time slot into the database
            cursor.execute("""
                INSERT INTO time_slots (slot_name, slot_hour, slot_minute, edit_interval)
                VALUES (%s, %s, %s, %s)
            """, (slot_name, slot_hour, slot_minute, edit_interval))
            connection.commit()
            flash("New time slot added successfully.", "success")

    # Fetch time slots for display
    cursor.execute("SELECT * FROM time_slots")
    time_slots = cursor.fetchall()

    connection.close()
    return render_template('manage_time_slots.html', time_slots=time_slots)


@app.route('/update_time_slot/<int:id>', methods=['POST'])
def update_time_slot(id):
    # Handle updating an existing time slot
    connection = get_db_connection()
    cursor = connection.cursor()
    
    slot_name = request.form['slot_name']
    slot_hour = request.form['slot_hour']
    slot_minute = request.form['slot_minute']
    edit_interval = request.form['edit_interval']

    # Update the time slot in the database
    cursor.execute("""
        UPDATE time_slots 
        SET slot_name = %s, slot_hour = %s, slot_minute = %s, edit_interval = %s
        WHERE id = %s
    """, (slot_name, slot_hour, slot_minute, edit_interval, id))
    connection.commit()
    connection.close()

    flash("Time slot updated successfully.", "success")
    return redirect(url_for('manage_time_slots'))

#route for managing assembly information
@app.route('/manage_assembly_info')
def manage_assembly_info():
    connection = get_db_connection()
    cursor = connection.cursor(pymysql.cursors.DictCursor)
    
    # Fetch assembly information from the database
    cursor.execute("""
        SELECT state_name, state_code, deo_district_name, deo_district_code, assembly_name, assembly_code
        FROM assembly_info
    """)
    assembly_info = cursor.fetchall()

    connection.close()
    return render_template('manage_assembly_info.html', assembly_info=assembly_info)

# Route to display the manage users page
@app.route('/manage_user_info')
def manage_user_info():
    connection = get_db_connection()
    cursor = connection.cursor(pymysql.cursors.DictCursor)
    cursor.execute("SELECT uid, name, username, user_type, mobile_number, password FROM user_info")
    users = cursor.fetchall()
    connection.close()
    
    # Debugging output to check if password is being retrieved
    print("Users data retrieved from database:", users)
    
    return render_template('manage_user_info.html', users=users)



# Route to add a new user
@app.route('/add_user', methods=['POST'])
def add_user():
    try:
        name = request.form['name']
        username = request.form['username']
        user_type = request.form['user_type']
        mobile_number = request.form['mobile_number']
        password = request.form['password']
        
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO user_info (name, username, user_type, mobile_number, password) 
            VALUES (%s, %s, %s, %s, %s)
        """, (name, username, user_type, mobile_number, password))
        connection.commit()
        flash('User added successfully', 'success')
    except Exception as e:
        flash(f"Error adding user: {e}", 'danger')
    finally:
        connection.close()
    return redirect(url_for('manage_users'))

# Route to update user information
@app.route('/update_user/<int:uid>', methods=['POST'])
def update_user(uid):
    try:
        name = request.form['name']
        username = request.form['username']
        user_type = request.form['user_type']
        mobile_number = request.form['mobile_number']
        password = request.form.get('password')

        # Establish database connection
        connection = get_db_connection()
        cursor = connection.cursor()

        # Update statement including password only if provided
        if password:
            cursor.execute("""
                UPDATE user_info 
                SET name = %s, username = %s, user_type = %s, mobile_number = %s, password = %s
                WHERE uid = %s
            """, (name, username, user_type, mobile_number, password, uid))
        else:
            cursor.execute("""
                UPDATE user_info 
                SET name = %s, username = %s, user_type = %s, mobile_number = %s
                WHERE uid = %s
            """, (name, username, user_type, mobile_number, uid))

        connection.commit()
        flash('User updated successfully', 'success')
    except Exception as e:
        flash(f"Error updating user: {e}", 'danger')
    finally:
        connection.close()
    return redirect(url_for('manage_user_info'))


# Route to delete a user
@app.route('/delete_user/<int:uid>', methods=['POST'])
def delete_user(uid):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM user_info WHERE uid = %s", (uid,))
        connection.commit()
        flash('User deleted successfully', 'success')
    except Exception as e:
        flash(f"Error deleting user: {e}", 'danger')
    finally:
        connection.close()
    return redirect(url_for('manage_users'))

# Route to handle user logout and clear session data
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Run the app in debug mode for development purposes
if __name__ == '__main__':
    app.run(debug=True)
