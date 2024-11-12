import pika
import logging

class RabbitMQClient:
    """
    RabbitMQ Client to handle asynchronous connection, publishing, and consuming of messages.
    Uses pika.SelectConnection for asynchronous communication with RabbitMQ.
    """

    def __init__(self, rabbitmq_url: str, queue: str, callback):
        """
        Initializes the RabbitMQClient with a connection URL, queue name, and message callback function.

        Parameters:
        - rabbitmq_url: str - RabbitMQ connection URL
        - queue: str - The name of the queue
        - callback: function - The function to call when a message is received
        """
        self.rabbitmq_url = rabbitmq_url
        self.queue = queue
        self.callback = callback
        self.connection = None
        self.channel = None

    def connect(self):
        """
        Establish an asynchronous connection to RabbitMQ and declare the queue.
        """
        self.connection = pika.SelectConnection(
            pika.URLParameters(self.rabbitmq_url),
            on_open_callback=self.on_connection_open,
            on_open_error_callback=self.on_connection_open_error,
            on_close_callback=self.on_connection_closed
        )

    def on_connection_open(self, connection):
        """
        Callback when the connection to RabbitMQ is successfully opened.
        """
        logging.info("RabbitMQ connection opened")
        self.connection.channel(on_open_callback=self.on_channel_open)

    def on_connection_open_error(self, connection, error):
        """
        Callback when there is an error opening the connection to RabbitMQ.
        """
        logging.error(f"Failed to open connection: {error}")
        self.reconnect()

    def on_connection_closed(self, connection, reason):
        """
        Callback when the connection to RabbitMQ is closed.
        """
        logging.warning(f"Connection closed: {reason}")
        self.reconnect()

    def on_channel_open(self, channel):
        """
        Callback when the channel is successfully opened.
        """
        logging.info("RabbitMQ channel opened")
        self.channel = channel
        self.channel.queue_declare(queue=self.queue, callback=self.on_queue_declared)

    def on_queue_declared(self, frame):
        """
        Callback when the queue is successfully declared.
        Starts consuming messages from the queue.
        """
        logging.info(f"Queue '{self.queue}' declared")
        self.channel.basic_consume(queue=self.queue, on_message_callback=self.callback, auto_ack=True)
        logging.info("Started consuming messages")

    def reconnect(self):
        """
        Reconnect to RabbitMQ in case of connection issues.
        """
        logging.info("Reconnecting to RabbitMQ")
        self.connect()

    def start(self):
        """
        Start the connection's I/O loop.
        """
        self.connect()
        try:
            self.connection.ioloop.start()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """
        Gracefully stop the connection's I/O loop.
        """
        if self.connection:
            self.connection.close()
            self.connection.ioloop.stop()
            logging.info("RabbitMQ connection closed and I/O loop stopped")
