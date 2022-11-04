import easyocr

reader = easyocr.Reader(['en']) 
# reader.

result = reader.readtext('chinese.jpg')