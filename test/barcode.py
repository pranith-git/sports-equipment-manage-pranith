import cv2
from pyzbar.pyzbar import decode


def start_barcode_scanner():
    print("Starting Barcode Scanner...")
    print("Press 'q' to exit\n")

    # Open webcam
    cap = cv2.VideoCapture(0)

    while True:
        success, frame = cap.read()

        if not success:
            print("Camera not detected")
            break

        # Detect barcodes
        barcodes = decode(frame)

        for barcode in barcodes:
            barcode_data = barcode.data.decode("utf-8")
            barcode_type = barcode.type

            # Draw rectangle around barcode
            x, y, w, h = barcode.rect
            cv2.rectangle(frame, (x, y),
                          (x + w, y + h),
                          (0, 255, 0), 2)

            text = f"{barcode_data} ({barcode_type})"

            cv2.putText(frame, text,
                        (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0), 2)

            print("Scanned Barcode:", barcode_data)

        cv2.imshow("Barcode Scanner", frame)

        # If any barcode(s) were detected, stop after showing result briefly
        if barcodes:
            # give a short moment for the user to see the detected barcode
            cv2.waitKey(1000)
            break

        # Press Q to quit manually
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    start_barcode_scanner()
