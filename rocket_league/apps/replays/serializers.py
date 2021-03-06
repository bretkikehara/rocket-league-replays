from rest_framework.serializers import (HyperlinkedModelSerializer,
                                        ReadOnlyField)

from .models import Component, Goal, Map, Player, Replay, ReplayPack, Season


class GoalSerializer(HyperlinkedModelSerializer):

    goal_time = ReadOnlyField()

    player_id = ReadOnlyField()

    class Meta:
        model = Goal


class PlayerSerializer(HyperlinkedModelSerializer):

    id = ReadOnlyField()

    class Meta:
        model = Player
        exclude = ['replay']


class MapSerializer(HyperlinkedModelSerializer):

    class Meta:
        model = Map


class SeasonSerializer(HyperlinkedModelSerializer):

    class Meta:
        model = Season


class ComponentSerializer(HyperlinkedModelSerializer):

    id = ReadOnlyField()

    class Meta:
        model = Component


class ReplaySerializer(HyperlinkedModelSerializer):

    id = ReadOnlyField()

    goal_set = GoalSerializer(
        many=True,
        read_only=True,
    )

    player_set = PlayerSerializer(
        many=True,
        read_only=True,
    )

    map = MapSerializer(
        many=False,
        read_only=True,
    )

    season = SeasonSerializer(
        many=False,
        read_only=True,
    )

    user_id = ReadOnlyField()

    class Meta:
        model = Replay
        exclude = ['user', 'crashed_heatmap_parser']
        depth = 1


class ReplayPackSerializer(HyperlinkedModelSerializer):

    id = ReadOnlyField()

    user_id = ReadOnlyField()

    replays = ReplaySerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = ReplayPack
        exclude = ['user']


class ReplayCreateSerializer(HyperlinkedModelSerializer):

    id = ReadOnlyField()

    def validate(self, attrs):
        instance = Replay(**attrs)
        instance.clean()
        return attrs

    class Meta:
        model = Replay
        fields = ['id', 'file', 'url', 'get_absolute_url']
        depth = 0
