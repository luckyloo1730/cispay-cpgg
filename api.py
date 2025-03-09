from flask import Flask, request, redirect, jsonify
from CISPay import CISPay
import requests
import threading
import mysql.connector
import time

client = CISPay('UUID')  # UUID вашего мерчанта

def createpay(amount, comment, expire):
    data = client.order_create(amount, comment, expire)
    return data

def check_payment_status_in_background(payment_uuid, userid, amount):
    timeout = 1830  # Timeout in seconds
    interval = 10  # Interval between checks
    elapsed_time = 0

    while elapsed_time < timeout:
        # Check the payment status through the API
        success = check_payment_status(payment_uuid)
        
        if success:
            print(f"Payment successful for user {userid}!")

            # Connect to the database
            con = mysql.connector.connect(
                host="127.0.0.1",
                user="controlpaneluser",
                password="password",
                database="controlpanel"
            )
            cur = con.cursor()

            # Fetch the user's current credits
            cur.execute("SELECT credits FROM users WHERE id = %s", (userid,))
            user_data = cur.fetchone()
            if not user_data:
                print(f"User {userid} not found in the database.")
                break
            user_credits = user_data[0]

            # Update the user's credits
            new_credits = user_credits + amount
            cur.execute("UPDATE users SET credits = %s WHERE id = %s", (new_credits, userid))

            # Check if the user has a referrer
            cur.execute("SELECT referral_id FROM user_referrals WHERE registered_user_id = %s", (userid,))
            referrer_data = cur.fetchone()
            if referrer_data:
                referrer_id = referrer_data[0]
                
                # Fetch the referrer's current credits
                cur.execute("SELECT credits FROM users WHERE id = %s", (referrer_id,))
                referrer_data = cur.fetchone()
                if referrer_data:
                    referrer_credits = referrer_data[0]
                    
                    # Calculate and update the referrer's credits
                    referral_bonus = amount * 0.15  # 15% of the payment amount
                    new_referrer_credits = referrer_credits + referral_bonus
                    cur.execute("UPDATE users SET credits = %s WHERE id = %s", (new_referrer_credits, referrer_id))

                    print(f"Referral bonus of {referral_bonus} added to referrer ID {referrer_id}.")

            con.commit()
            con.close()
            break

        time.sleep(interval)
        elapsed_time += interval

    if not success:
        print("Payment was not completed within the allotted time.")
    timeout = 1830  # Время ожидания в секундах
    interval = 10  # Интервал между проверками
    elapsed_time = 0

    while elapsed_time < timeout:
        # Выполняем проверку платежа через API
        success = check_payment_status(payment_uuid)
        
        if success:
            # Если оплата успешна, выполнить нужные действия
            user = getuser(userid)
            user_id, name, email, server_limit, credits = user
            print('Оплачен!')

            con = mysql.connector.connect(
                host="127.0.0.1",       # Адрес сервера
                user="controlpaneluser",   # Имя пользователя
                password="password",
                database="controlpanel", # Имя базы данных
                charset="utf8mb4",  # Задаем charset
                collation="utf8mb4_general_ci"  # Указываем другую кодировку
            )

            cur = con.cursor()
            cur.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
            credits = cur.fetchone()[0]

           # if amount >= 1000:
           #     bonus = amount * 0.15
           # elif amount >= 500:
           #     bonus = amount * 0.10
           # elif amount >= 300:
           #     bonus = amount * 0.05
           # else:
           #     bonus = 0

            newcredits = int(credits)+int(amount)
# + int(bonus)
	    # Для скидок
            #cur.execute("UPDATE users SET credits = %s * 1.30 WHERE id = %s", (newcredits, user_id))
            cur.execute("UPDATE users SET credits = %s WHERE id = %s", (newcredits, user_id))
            cur.execute("UPDATE users SET role = 'client' WHERE id = %s", (user_id,))
            cur.execute("UPDATE users SET server_limit = 50 WHERE id = %s", (user_id,))
            con.commit()
            con.close()
            break

        time.sleep(interval)
        elapsed_time += interval

    if not success:
        print("Оплата не была завершена за отведённое время.")

def check_payment_status(payment_uuid):
    data = client.order_info(payment_uuid)
    
    pay_status = data['status']
    if pay_status == 'success':
        return True
    else:
        return False

def getuser(user_id):
    url = f'https://domain.com/api/users/{user_id}'
    headers = {
        'Authorization': 'Bearer YOUR_BEARER_TOKEN',  # Замените YOUR_BEARER_TOKEN на ваш фактический токен
        'Accept': 'application/json'
    }
    
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        
        if data:
            name = data['name']
            role = data['role']
            email = data['email']
            server_limit = data['server_limit']
            credits = data['credits']
            return user_id, name, email, server_limit, credits
    else:
        print(f"Ошибка при запросе: {response.status_code}")

app = Flask(__name__)

@app.route('/process', methods=['GET'])
def process_data():
    userid = request.args.get('id')
    amount = request.args.get('amount')
    
    if not userid or not amount:
        return jsonify({'error': 'Параметры id и amount обязательны!'}), 400
    
    try:
        amount = int(amount)
    except ValueError:
        return jsonify({'error': 'Некорректное значение amount!'}), 400
    
    comment = 'Balance Top Up'
    expire = 30
    
    # Создаем оплату через CISPay
    payment_data = createpay(amount, comment, expire)
    print('Платеж от', userid, amount)

    if payment_data and 'url' in payment_data:
        # Запускаем фоновую проверку статуса платежа
        payment_uuid = payment_data['uuid']
        threading.Thread(target=check_payment_status_in_background, args=(payment_uuid, userid, amount)).start()
        
        # Перенаправляем пользователя на страницу оплаты
        return redirect(payment_data['url'])

    return jsonify({'error': 'Ошибка создания оплаты'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=1488, debug=True)
