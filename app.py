from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_jwt_extended import JWTManager, create_access_token, jwt_required
from requests_oauthlib import OAuth2Session
from datetime import datetime, timedelta
from flask_socketio import SocketIO
from flask_session import Session
from dotenv import load_dotenv
from flask_cors import CORS
import mysql.connector
import requests
import json
import os


load_dotenv()
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # allow http for local dev for now. can deal later.


app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))
socketio = SocketIO(app, cors_allowed_origins="*")


# cors(app)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)


# jwt config
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
print("JWT Secret Key:", app.config['JWT_SECRET_KEY'])


jwt = JWTManager(app)

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('MYSQL_HOST'),
        user=os.getenv('MYSQL_USER'),
        password=os.getenv('MYSQL_PASSWORD'),
        database=os.getenv('MYSQL_DB')
    )


# google oauth config
app.secret_key = os.getenv("SECRET_KEY")
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL).json()


# admin credentials (plaintext for simplicity , maybe change later?!)
ADMIN_USER = 'admin'
ADMIN_PASS = 'adminpass'

# better verification!!!!
@app.route('/health')
def health():
    return "OK", 200


# api login route
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    print("LOGIN ATTEMPT:", data)

    if data['username'] != ADMIN_USER or data['password'] != ADMIN_PASS:
        return jsonify({"msg": "Invalid credentials"}), 401

    access_token = create_access_token(identity=data['username'])
    return jsonify(access_token=access_token), 200

@app.route('/login', methods=['OPTIONS'])
def login_options():
    return '', 204

@app.route('/log', methods=['POST'])
def log_test():
    print("Postman reached Flask!")
    return "OK", 200


# creates deals
@app.route('/deals', methods=['POST'])
@jwt_required()
def create_deal():
    data = request.get_json()
    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        INSERT INTO deals 
        (title, price, expiry_date, promotion, description, affiliate_link, category)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    cursor.execute(query, (
        data['title'],
        data['price'],
        data['expiry_date'],
        data['promotion'],
        data['description'],
        data['affiliate_link'],
        data.get('category')
    ))

    connection.commit()
    # broadcast new deal to viewers
    deal_info = {
        "title": data["title"],
        "price": data["price"],
        "expiry_date": data["expiry_date"],
        "promotion": data["promotion"],
        "description": data["description"],
        "affiliate_link": data["affiliate_link"],
        "category": data.get("category", "")
    }
    socketio.emit('new_deal', deal_info, namespace="/")

    cursor.close()
    connection.close()
    return jsonify({"message": "Deal created"}), 201


# simple get api
@app.route('/deals', methods=['GET'])
def get_deals():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT * FROM deals")
    deals = cursor.fetchall()

    cursor.close()
    connection.close()
    return jsonify(deals), 200

# get a specific deal by id
@app.route('/deals/<int:dealid>', methods=['GET'])
def get_deal(dealid):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT * FROM deals WHERE dealid = %s", (dealid,))
    deal = cursor.fetchone()

    cursor.close()
    connection.close()

    if deal:
        return jsonify(deal), 200
    return jsonify({"message": "Deal not found"}), 404

# modify deals
@app.route('/deals/<int:dealid>', methods=['PUT'])
@jwt_required()
def update_deal(dealid):
    data = request.get_json()
    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        UPDATE deals 
        SET title=%s, price=%s, expiry_date=%s, 
            promotion=%s, description=%s, affiliate_link=%s, category=%s
        WHERE dealid=%s
    """
    cursor.execute(query, (
        data['title'],
        data['price'],
        data['expiry_date'],
        data['promotion'],
        data['description'],
        data['affiliate_link'],
        data.get('category'),
        dealid
    ))

    connection.commit()
    updated_info = {
        "dealid": dealid,
        "title": data["title"],
        "price": data["price"],
        "expiry_date": data["expiry_date"],
        "promotion": data["promotion"],
        "description": data["description"],
        "affiliate_link": data["affiliate_link"],
        "category": data.get("category", "")
    }
    socketio.emit("deal_updated", updated_info, namespace="/")

    cursor.close()
    connection.close()
    return jsonify({"message": "Deal updated"}), 200

# delete the deal
@app.route('/deals/<int:dealid>', methods=['DELETE'])
@jwt_required()
def delete_deal(dealid):
    connection = get_db_connection()
    cursor = connection.cursor()

    # first remove from saved_deals (child table)
    cursor.execute("DELETE FROM saved_deals WHERE deal_id = %s", (dealid,))
    connection.commit()

    # then remove from deals (parent table)
    cursor.execute("DELETE FROM deals WHERE dealid = %s", (dealid,))
    connection.commit()
    socketio.emit("deal_deleted", {"dealid": dealid}, namespace="/")

    cursor.close()
    connection.close()
    return jsonify({"message": "Deal deleted"}), 200

## now filters, sorts, saves and tracks!
@app.route('/viewer')
def viewer():
    if "user" not in session:
        return render_template('viewer_login.html')

    # --- filters & sorting ---
    filter_option = request.args.get("filter")
    sort_by = request.args.get("sort_by")
    sort_order = request.args.get("sort_order", "asc")
    category = request.args.get("category")

    query = "SELECT * FROM deals WHERE 1=1"
    params = []

    if filter_option == "under50":
        query += " AND price < 50"
    elif filter_option == "this_week":
        next_week = (datetime.utcnow() + timedelta(days=7)).date()
        query += " AND expiry_date <= %s"
        params.append(next_week)
    elif filter_option == "this_month":
        next_month = (datetime.utcnow().replace(day=28) + timedelta(days=4)).replace(day=1)
        query += " AND expiry_date <= %s"
        params.append(next_month.date())

    if category:
        query += " AND category = %s"
        params.append(category)

    if sort_by in ["price", "expiry_date"]:
        query += f" ORDER BY {sort_by} {sort_order.upper()}"

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # --- get all filtered deals ---
    cursor.execute(query, tuple(params))
    deals = cursor.fetchall()

    # --- get current user's saved deal ids ---
    email = session["user"]["email"]
    cursor.execute("SELECT id FROM customers WHERE email = %s", (email,))
    customer = cursor.fetchone()
    saved_ids = []

    if customer:
        cursor.execute("SELECT deal_id FROM saved_deals WHERE customer_id = %s", (customer["id"],))
        saved = cursor.fetchall()
        saved_ids = [s["deal_id"] for s in saved]

    # --- get top 5 trending deals (most saved) ---
    cursor.execute("""
        SELECT d.*, COUNT(s.id) as save_count
        FROM deals d
        JOIN saved_deals s ON d.dealid = s.deal_id
        GROUP BY d.dealid
        ORDER BY save_count DESC
        LIMIT 5
    """)
    trending_deals = cursor.fetchall()

    # --- get distinct categories for dropdown ---
    cursor.execute("SELECT DISTINCT category FROM deals WHERE category IS NOT NULL AND category != ''")
    all_categories = [row["category"] for row in cursor.fetchall()]

    cursor.close()
    connection.close()

    # --- render template with all data ---
    return render_template(
        'viewer.html',
        user=session["user"],
        deals=deals,
        saved_ids=saved_ids,
        trending_deals=trending_deals,
        all_categories=all_categories
    )

# dedicated viewer section
@app.route('/viewer/profile')
def viewer_profile():
    if "user" not in session:
        return redirect("/viewer")

    email = session["user"]["email"]
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT * FROM customers WHERE email = %s", (email,))
    user = cursor.fetchone()

    # get saved deal count
    cursor.execute("SELECT COUNT(*) as saved_count FROM saved_deals WHERE customer_id = %s", (user["id"],))
    saved_count = cursor.fetchone()["saved_count"]

    # get category preferences
    cursor.execute("""
        SELECT d.category, COUNT(*) as count
        FROM saved_deals s
        JOIN deals d ON s.deal_id = d.dealid
        WHERE s.customer_id = %s AND d.category IS NOT NULL
        GROUP BY d.category
        ORDER BY count DESC
    """, (user["id"],))
    category_stats = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template("viewer_profile.html",
                           user=session["user"],
                           saved_count=saved_count,
                           category_stats=category_stats)

# modify user details (for now name)
@app.route('/viewer/update_name', methods=['POST'])
def update_name():
    if "user" not in session:
        return jsonify({"message": "Unauthorized"}), 403

    new_name = request.json.get("name", "").strip()
    if not new_name:
        return jsonify({"message": "Name cannot be empty"}), 400

    email = session["user"]["email"]
    connection = get_db_connection()
    cursor = connection.cursor()

    # update name in db
    cursor.execute("UPDATE customers SET name = %s WHERE email = %s", (new_name, email))
    connection.commit()

    # update session too
    session["user"]["name"] = new_name

    cursor.close()
    connection.close()

    return jsonify({"message": "Name updated successfully"})


## save a deal
@app.route('/save/<int:dealid>')
def save_deal(dealid):
    if "user" not in session:
        return redirect("/viewer")

    # get customer id from db using session email
    email = session["user"]["email"]
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT id FROM customers WHERE email = %s", (email,))
    customer = cursor.fetchone()

    if customer:
        customer_id = customer[0]

        # try to insert saved deal. ignore if already exists.
        try:
            cursor.execute(
                "INSERT INTO saved_deals (customer_id, deal_id) VALUES (%s, %s)",
                (customer_id, dealid)
            )
            connection.commit()
        except mysql.connector.errors.IntegrityError:
            # already saved. should toggle removal here if you want?! maybe later.
            pass

    cursor.close()
    connection.close()
    return redirect("/viewer")

## unsave a deal
@app.route('/unsave/<int:dealid>')
def unsave_deal(dealid):
    if "user" not in session:
        return redirect("/viewer")

    email = session["user"]["email"]
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT id FROM customers WHERE email = %s", (email,))
    customer = cursor.fetchone()

    if customer:
        customer_id = customer[0]
        cursor.execute(
            "DELETE FROM saved_deals WHERE customer_id = %s AND deal_id = %s",
            (customer_id, dealid)
        )
        connection.commit()

    cursor.close()
    connection.close()
    return redirect("/viewer")

## view all saved deals
@app.route('/viewer/saved')
def viewer_saved():
    if "user" not in session:
        return redirect("/viewer")

    email = session["user"]["email"]
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT id FROM customers WHERE email = %s", (email,))
    customer = cursor.fetchone()

    if customer:
        customer_id = customer["id"]
        cursor.execute("""
            SELECT d.* FROM deals d
            JOIN saved_deals s ON d.dealid = s.deal_id
            WHERE s.customer_id = %s
        """, (customer_id,))
        saved_deals = cursor.fetchall()
    else:
        saved_deals = []

    cursor.close()
    connection.close()

    return render_template('viewer_saved.html', user=session["user"], deals=saved_deals)


## just to see if something turns up or not
@app.route('/ping')
def ping():
    return "pong", 200


## ADMIN AREA

# admin login handle
@app.route('/admin/login')
def admin_login():
    return render_template('admin_login.html')

# admin home
@app.route('/admin/dashboard')
def admin_dashboard():
    return render_template('admin_dashboard.html')

# add deals
@app.route('/admin/add')
def admin_add():
    return render_template('admin_add.html')

# modify deals
@app.route('/admin/edit/<int:dealid>')
def admin_edit(dealid):
    return render_template('admin_edit.html')

# renders the stats page. this is NOT PROTECTED by jwt
@app.route('/admin/stats/view')
def admin_stats_page():
    return render_template("admin_stats.html")

# sends json stats and it's PROTECTED
@app.route('/admin/stats')
@jwt_required()
def admin_stats_api():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) as total FROM customers")
    total_customers = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM deals")
    total_deals = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT d.title, COUNT(s.id) AS save_count
        FROM deals d
        JOIN saved_deals s ON d.dealid = s.deal_id
        GROUP BY d.dealid
        ORDER BY save_count DESC
        LIMIT 5
    """)
    top_saved_deals = cursor.fetchall()

    cursor.execute("""
        SELECT d.title, d.click_count as clicks FROM deals d
        ORDER BY d.click_count DESC
        LIMIT 5
    """)
    deal_clicks = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify({
        "total_customers": total_customers,
        "total_deals": total_deals,
        "top_saved_deals": top_saved_deals,
        "deal_clicks": deal_clicks
    })

# user click count tracking
@app.route('/click/<int:dealid>')
def track_click_and_redirect(dealid):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # increment click_count
    cursor.execute("UPDATE deals SET click_count = click_count + 1 WHERE dealid = %s", (dealid,))
    connection.commit()

    # get the affiliate link
    cursor.execute("SELECT affiliate_link FROM deals WHERE dealid = %s", (dealid,))
    result = cursor.fetchone()

    cursor.close()
    connection.close()

    if result and result["affiliate_link"]:
        return redirect(result["affiliate_link"])
    else:
        return "Deal not found or missing link.", 404


## CLIENT GOOGLE LOGIN AREA

@app.route("/customer/login")
def customer_login():
    redirect_uri = request.args.get("redirect", "/viewer")

    google_provider_cfg = get_google_provider_cfg()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]

    google = OAuth2Session(
        GOOGLE_CLIENT_ID,
        redirect_uri=url_for("customer_callback", _external=True),
        scope=["openid", "email", "profile"]
    )

    authorization_url, state = google.authorization_url(
        authorization_endpoint,
        access_type="offline",
        prompt="select_account"
    )

    session["oauth_state"] = state
    session["post_login_redirect"] = redirect_uri  # store where to go after login
    return redirect(authorization_url)

# now stores user data to the db
@app.route("/customer/callback")
def customer_callback():
    google_provider_cfg = get_google_provider_cfg()
    token_endpoint = google_provider_cfg["token_endpoint"]

    google = OAuth2Session(
        GOOGLE_CLIENT_ID,
        state=session["oauth_state"],
        redirect_uri=url_for("customer_callback", _external=True)
    )

    token = google.fetch_token(
        token_endpoint,
        client_secret=GOOGLE_CLIENT_SECRET,
        authorization_response=request.url,
    )

    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    userinfo_response = google.get(userinfo_endpoint).json()

    email = userinfo_response["email"]
    name = userinfo_response["name"]
    picture = userinfo_response["picture"]

    # save to db if this user is new
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM customers WHERE email = %s", (email,))
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            "INSERT INTO customers (email, name, picture) VALUES (%s, %s, %s)",
            (email, name, picture)
        )
        connection.commit()

    cursor.close()
    connection.close()

    session["user"] = {
        "email": email,
        "name": name,
        "picture": picture
    }

    return redirect(session.get("post_login_redirect", "/viewer"))


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/viewer')


if __name__ == '__main__':
    socketio.run(app, debug=True, port=5050)

