import os, datetime, time
import pkg_resources
from flask import Flask, request, render_template, redirect, url_for,  session, send_from_directory, flash
from flask_security import Security, UserMixin, RoleMixin ,SQLAlchemyUserDatastore ,current_user, login_required
from flask_sqlalchemy import SQLAlchemy


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI']='sqlite:///Konta.db'
app.config['SECRET_KEY'] =os.environ.get('SECRET_KEY','developerskie')
app.config['SECURITY_PASSWORD_SALT']=os.environ.get('SECURITY_PASSWORD_SALT','jakas-sol')
app.config['SECURITY_REGISTERABLE'] = True
app.config['SECURITY_SEND_REGISTER_EMAIL']=False
db=SQLAlchemy(app)



roles_user = db.Table(
    'roles_users',
    db.Column('user_id',db.ForeignKey('user.id')),
    db.Column('role_id',db.ForeignKey('role.id'))
)

class Zamowienie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cena = db.Column(db.Float)
    paragon_path = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    address = db.Column(db.String(255))

class Produkt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nazwa = db.Column(db.String(255))
    cena = db.Column(db.Float)
    opis = db.Column(db.String(255))
    zdjecie = db.Column(db.String(255))

    @staticmethod
    def load_from_file(file_path):
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                parts = line.strip().split('/', 3)
                if len(parts) == 4:
                    id, nazwa, cena, opis = parts
                    if not Produkt.query.get(int(id)):
                        produkt = Produkt(
                            id=int(id),
                            nazwa=nazwa.strip('"'),
                            cena=float(cena.replace(',', '.')),
                            opis=opis.strip('"'),
                            zdjecie=f'images/{id}.jpg'
                        )
                        db.session.add(produkt)
            db.session.commit()

class Role(db.Model, RoleMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True)
    description = db.Column(db.String(128))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=True)
    password = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, default=True)
    confirmed_at = db.Column(db.DateTime)
    fs_uniquifier = db.Column(db.String(255), unique=True, nullable=False)
    roles = db.relationship('Role', secondary=roles_user, backref=db.backref('users'))
    zamowienia = db.relationship('Zamowienie', backref='user')


    def __init__(self, **kwargs)->None:
        super().__init__(**kwargs)
        if not self.fs_uniquifier:
            import uuid
            self.fs_uniquifier = str(uuid.uuid4())
user_datastore = SQLAlchemyUserDatastore(db,User,Role)
security=Security(app, user_datastore)   



@app.route("/")
def index():
    return render_template('index.html')

@app.route("/zamow", methods=['GET', 'POST'])
@login_required
def zamow():
    if 'cart' not in session:
        session['cart'] = {}

    if request.method == 'POST':
        if 'remove' in request.form:
            produkt_id = request.form.get('produkt_id')
            if produkt_id in session['cart']:
                del session['cart'][produkt_id]
                session.modified = True
        else:
            produkt_id = request.form.get('produkt_id')
            ilosc = int(request.form.get('quantity', 1))
            if produkt_id:
                if produkt_id in session['cart']:
                    session['cart'][produkt_id] += ilosc
                else:
                    session['cart'][produkt_id] = ilosc
                session.modified = True
            

    produkty = Produkt.query.all() 
    return render_template('zamow.html', produkty=produkty, cart=session['cart'])

@app.route("/koszyk", methods=['GET', 'POST'])
@login_required
def koszyk():
    if 'cart' not in session:
        session['cart'] = {}
    suma_cala = sum(produkt.cena * quantity for produkt_id, quantity in session['cart'].items() for produkt in Produkt.query.filter_by(id=produkt_id))
    suma_cala = round(suma_cala, 2)
    address = session.get('address', None)
    if request.method == 'POST':
        if 'submit_address' in request.form:
            address = request.form.get('address')
            session['address'] = address
            flash('Adres został zapisany!', 'success')
        elif 'place_order' in request.form and address!=None:
            if session['cart']:
                zamowienie = Zamowienie()
                data_zamowienia = datetime.datetime.now()
                zamowienie.cena = sum(produkt.cena * quantity for produkt_id, quantity in session['cart'].items() for produkt in Produkt.query.filter_by(id=produkt_id))
                zamowienie.cena=round(zamowienie.cena, 2)
                zamowienie.address = address
                order_details = f"Data zamówienia: {data_zamowienia.strftime("%c")}\nCena: {zamowienie.cena} PLN \nAdres:{zamowienie.address}\nProdukty:\n"
                for produkt_id, quantity in session['cart'].items():
                    produkt = Produkt.query.get(produkt_id)
                    order_details += f"{produkt.nazwa} - {quantity} x {produkt.cena} PLN\n"

                temp= int(data_zamowienia.timestamp())
                paragon_filename = f"temp/paragony/paragon_{temp}.txt"
                paragon_path = os.path.join(paragon_filename)
                with open(paragon_path, 'w') as file:
                    file.write(order_details)



                zamowienie.paragon_path = paragon_filename
                zamowienie.user_id = current_user.id
                db.session.add(zamowienie)
                db.session.commit()

                session['cart'] = {}
                flash(f'Zamówienie złożone pomyślnie!', 'success')
                return redirect(url_for('index'))
            elif 'place_order' in request.form and address==None:
                flash('Nie podano adresu!', 'danger')

    produkty = Produkt.query.filter(Produkt.id.in_(session['cart'].keys())).all()
    return render_template('koszyk.html', produkty=produkty, cart=session['cart'],suma_cala=suma_cala,address=address)

@app.route("/konto")
@login_required
def konto():
    zamowienia = Zamowienie.query.filter_by(user_id=current_user.id).all()
    lista_zamowien = []
    for zamowienie in zamowienia:
        with open(zamowienie.paragon_path, 'r') as file:
            paragon_content = file.read()
            lista_zamowien.append(paragon_content)
    return render_template('konto.html', lista_zamowien=lista_zamowien)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        Produkt.load_from_file('static/fooddb.txt')
        if (not os.path.exists('temp/paragony')):
            os.makedirs('temp/paragony')
    app.run(host='0.0.0.0', port=90, debug=True)
    
