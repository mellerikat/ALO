import redis
import redis.asyncio 

class RedisList:
    """Redis Lists are an ordered list, FIFO Queue.
    Redis List allows pushing new elements on the head (on the left) of the list.
    The maximum length of a list is 4,294,967,295.
    ref: https://redis.io/docs/latest/develop/data-types/lists/
    """
    def __init__(self, **redis_kwargs):
        """ Initializes the Redis connection with provided connection parameters.
        
        Args: 
            host (str): redis host uri - e.g. 'localhost'
            port (int): redis port - e.g. 6379
            db   (int): redis database number - e.g. 0

        Returns: -

        """
        self.redis = redis.Redis(**redis_kwargs)

    def size(self, key):
        """ Returns the size of the queue identified by 'key'.
        
        Args: 
            key (str): channel name 

        Returns: -

        """
        return self.redis.llen(key)

    def isEmpty(self, key):
        """ Checks if the queue identified by 'key' is empty.
        
        Args: 
            key (str): channel name 

        Returns: -

        """
        return self.size(key) == 0

    def lput(self, key, element):
        """ Insert an element at the head (left) of the queue.
        
        Args: 
            key     (str): channel name 
            element (str, int..): element tobe left-pushed 

        Returns: -

        """
        self.redis.lpush(key, element)

    def rget(self, key, isBlocking=False, timeout=None):
        """ Retrieves and removes the last (rightmost) element from the queue.
        
        Args: 
            key         (str): channel name 
            isBlocking  (bool): whether to block 
            timeout      (bool): blocking timeout

        Returns: 
            right-pop element

        """
        if isBlocking:
            element = self.redis.brpop(key, timeout=timeout)
            return element[1] if element else None
        else:
            return self.redis.rpop(key)

    def rput(self, key, element):
        """ Inserts an element at the tail (right) of the queue.
        
        Args: 
            key     (str): channel name 
            element (str, int..): element tobe right-pushed 

        Returns: -

        """
        self.redis.rpush(key, element)

    def lget(self, key, isBlocking=False, timeout=None):
        """ Retrieves and removes the first (leftmost) element from the queue.
        
        Args: 
            key         (str): channel name 
            isBlocking  (bool): whether to block 
            timeout      (bool): blocking timeout

        Returns: 
            left-pop element
        """
        if isBlocking:
            element = self.redis.blpop(key, timeout=timeout)
            return element[1] if element else None
        else:
            return self.redis.lpop(key)

    def get_without_pop(self, key):
        """ Retrieves the last (rightmost) element without removing it from the queue.
        
        Args: 
            key     (str): channel name 

        Returns: 
            last element

        """
        return self.redis.lindex(key, -1)

    def get_without_pop_index(self, key, index):
        """ Retrieves an element by index without removing it from the queue.
        
        Args: 
            key     (str): channel name 

        Returns: 
            last element by index

        """
        return self.redis.lindex(key, index)

    def clean_queue(self, key):
        """ Removes all elements from the queue identified by 'key'.
        
        Args: 
            key     (str): channel name 

        Returns: -

        """
        while not self.isEmpty(key):
            self.lget(key)


class RedisPubSub:
    """ Utilizes Redis's Pub/Sub feature to synchronously subscribe and publish messages.
    """
    def __init__(self, **redis_kwargs):
        """ Initialize an instance of the RedisPubSub class.
        
        Args: 
            host (str): redis host uri - e.g. 'localhost'
            port (int): redis port - e.g. 6379
            db   (int): redis database number - e.g. 0

        Returns: -

        """
        self.redis = redis.StrictRedis(**redis_kwargs)
        self.pubsub = None

    def publish(self, channel: str, message: str):
        """ Publish a message synchronously to the specified channel.
        
        Args:
            channel (str): message channel name
            message (str): message published 
        
        Returns: 
            reids publish object
        
        """
        return self.redis.publish(channel, message)
 
    def subscribe(self, channel: str):
        """ Subscribe a message synchronously to the specified channel.
        
        Args:
            channel (str): message channel name
        
        Returns: 
            reids subscribe object
        
        """
        if self.pubsub is None:
            self.pubsub = self.redis.pubsub()
        return self.pubsub.subscribe(channel)


