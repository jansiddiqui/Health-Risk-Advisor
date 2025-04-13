from flask import Flask, render_template, request, send_file
import skfuzzy as fuzz
from skfuzzy import control as ctrl
import csv
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os

app = Flask(__name__)

# Define fuzzy variables
temperature = ctrl.Antecedent(np.arange(95, 106, 1), 'temperature')
heart_rate = ctrl.Antecedent(np.arange(40, 161, 1), 'heart_rate')
cough = ctrl.Antecedent(np.arange(0, 11, 1), 'cough')
risk = ctrl.Consequent(np.arange(0, 101, 1), 'risk')

# Membership functions for temperature
temperature['low'] = fuzz.trimf(temperature.universe, [95, 95, 98])
temperature['normal'] = fuzz.trimf(temperature.universe, [97, 98.6, 100])
temperature['high'] = fuzz.trimf(temperature.universe, [99, 102, 105])

# Heart rate
heart_rate['low'] = fuzz.trimf(heart_rate.universe, [40, 40, 60])
heart_rate['normal'] = fuzz.trimf(heart_rate.universe, [60, 80, 100])
heart_rate['high'] = fuzz.trimf(heart_rate.universe, [90, 130, 160])

# Cough
cough['none'] = fuzz.trimf(cough.universe, [0, 0, 3])
cough['moderate'] = fuzz.trimf(cough.universe, [2, 5, 7])
cough['severe'] = fuzz.trimf(cough.universe, [6, 10, 10])

# Risk output
risk['low'] = fuzz.trimf(risk.universe, [0, 0, 35])
risk['medium'] = fuzz.trimf(risk.universe, [30, 50, 70])
risk['high'] = fuzz.trimf(risk.universe, [65, 100, 100])

# Define rules
rules = [
    ctrl.Rule(temperature['normal'] & heart_rate['normal'] & cough['none'], risk['low']),
    ctrl.Rule(temperature['high'] & heart_rate['high'] & cough['severe'], risk['high']),
    ctrl.Rule(temperature['high'] & cough['moderate'], risk['medium']),
    ctrl.Rule(temperature['low'] & heart_rate['low'], risk['medium']),
    ctrl.Rule(temperature['high'] & heart_rate['normal'] & cough['none'], risk['medium']),
    ctrl.Rule(cough['severe'] & heart_rate['high'], risk['high']),
    ctrl.Rule(cough['moderate'] & heart_rate['normal'], risk['medium']),
]

risk_ctrl = ctrl.ControlSystem(rules)
risk_sim = ctrl.ControlSystemSimulation(risk_ctrl)

# Store the last result to use in PDF
last_result = {}

def save_to_csv(temperature, heart_rate, cough, risk_score, category):
    filename = 'user_data.csv'
    fields = ['Timestamp', 'Temperature', 'Heart Rate', 'Cough Severity', 'Risk Score', 'Category']
    data = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), temperature, heart_rate, cough, risk_score, category]

    try:
        with open(filename, 'a', newline='') as f:
            writer = csv.writer(f)
            if f.tell() == 0:
                writer.writerow(fields)
            writer.writerow(data)
    except Exception as e:
        print(f"❌ Error saving to CSV: {e}")

@app.route('/', methods=['GET', 'POST'])
def index():
    global last_result
    result = None
    category = None

    if request.method == 'POST':
        try:
            temp = float(request.form['temperature'])
            hr = float(request.form['heart_rate'])
            cough_lvl = float(request.form['cough'])

            if not (95 <= temp <= 105):
                raise ValueError("Temperature must be between 95°F and 105°F.")
            if not (40 <= hr <= 160):
                raise ValueError("Heart rate must be between 40 and 160 BPM.")
            if not (0 <= cough_lvl <= 10):
                raise ValueError("Cough severity must be between 0 and 10.")

            sim = ctrl.ControlSystemSimulation(risk_ctrl)
            sim.input['temperature'] = temp
            sim.input['heart_rate'] = hr
            sim.input['cough'] = cough_lvl

            sim.compute()
            result = round(sim.output['risk'], 2)

            if result < 35:
                category = "Low"
            elif result < 70:
                category = "Medium"
            else:
                category = "High"

            save_to_csv(temp, hr, cough_lvl, result, category)

            last_result = {
                'temperature': temp,
                'heart_rate': hr,
                'cough': cough_lvl,
                'score': result,
                'category': category,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            return render_template('index.html', result=result, category=category)

        except Exception as e:
            return render_template('index.html', error=str(e), result=None, category=None)

    # GET request
    last_result = {}
    return render_template('index.html', result=None, category=None)


@app.route('/download')
def download_pdf():
    global last_result
    if not last_result:
        return "No result available to download. Please check your health first.", 400

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Title Section
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 60, "Health Risk Assessment Report")
    c.setFont("Helvetica", 12)
    c.drawCentredString(width / 2, height - 80, "Generated by Intelligent Health Monitoring System")

    # Horizontal line
    c.setStrokeColorRGB(0, 0, 0)
    c.line(50, height - 90, width - 50, height - 90)

    # Date and time
    c.setFont("Helvetica", 11)
    c.drawString(50, height - 115, f"Report generated on: {last_result['timestamp']}")

    # Section 1: Introduction
    y = height - 150
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, y, "1. Patient Vital Information")
    y -= 20
    c.setFont("Helvetica", 11)
    c.drawString(60, y, f"• Body Temperature: {last_result['temperature']} °F")
    y -= 18
    c.drawString(60, y, f"• Heart Rate: {last_result['heart_rate']} beats per minute")
    y -= 18
    c.drawString(60, y, f"• Cough Severity (scale 0-10): {last_result['cough']}")

    # Section 2: Risk Analysis
    y -= 40
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, y, "2. Risk Assessment Summary")
    y -= 20
    c.setFont("Helvetica", 11)
    c.drawString(60, y, f"Based on the input data, the system has computed an estimated health risk score.")
    y -= 18
    c.drawString(60, y, f"• Risk Score: {last_result['score']} out of 100")
    y -= 18

    # Risk level with brief interpretation
    category_text = {
        "Low": "This indicates minimal signs of health concern at the moment. No immediate action is required.",
        "Medium": "Moderate health indicators detected. Monitoring and rest are recommended. Consult a doctor if symptoms persist.",
        "High": "Significant health indicators observed. Immediate medical consultation is advised."
    }

    risk_level = last_result['category']
    interpretation = category_text.get(risk_level, "No interpretation available.")

    c.drawString(60, y, f"• Risk Category: {risk_level}")
    y -= 25
    c.setFont("Helvetica-Oblique", 11)
    c.drawString(60, y, interpretation)

    # Section 3: Recommendations
    y -= 45
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, y, "3. General Recommendations")
    y -= 20
    c.setFont("Helvetica", 11)
    rec_lines = [
        "• Ensure adequate hydration and rest.",
        "• Maintain a healthy diet and monitor symptoms over the next 24-48 hours.",
        "• Seek medical advice if symptoms worsen or new symptoms appear.",
        "• Avoid self-medication without professional consultation."
    ]
    for line in rec_lines:
        c.drawString(60, y, line)
        y -= 18

    # Footer
    y -= 20
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(50, y, "Disclaimer: This report is generated by a fuzzy logic-based system and is for informational purposes only.")
    y -= 12
    c.drawString(50, y, "For accurate diagnosis and treatment, please consult a certified healthcare provider.")

    c.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="health_risk_assessment_report.pdf",
        mimetype='application/pdf'
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
