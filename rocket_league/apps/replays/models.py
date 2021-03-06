import logging
import math
import re
from itertools import zip_longest

import bitstring
from django.conf import settings
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from django.utils.timezone import now
from pyrope import Replay as Pyrope
from social.apps.django_app.default.fields import JSONField

from .parser import parse_replay_header, parse_replay_netstream

logger = logging.getLogger('rocket_league')

PRIVACY_PRIVATE = 1
PRIVACY_UNLISTED = 2
PRIVACY_PUBLIC = 3

PLATFORM_UNKNOWN = 0
PLATFORM_STEAM = 1
PLATFORM_PSN = 2
PLATFORM_XBOX = 4
PLATFORM_SWITCH = 6

PLATFORMS = {
    'Unknown': PLATFORM_UNKNOWN,
    'Steam': PLATFORM_STEAM,
    'PlayStation': PLATFORM_PSN,
    'Xbox': PLATFORM_XBOX,
    'Switch': PLATFORM_SWITCH,
}

PLATFORMS_MAPPINGS = {
    'unknown': PLATFORM_UNKNOWN,
    'steam': PLATFORM_STEAM,
    'Steam': PLATFORM_STEAM,
    'PlayStation': PLATFORM_PSN,
    'playstation': PLATFORM_PSN,
    'ps4': PLATFORM_PSN,
    'Xbox': PLATFORM_XBOX,
    'xbox': PLATFORM_XBOX,
    'xboxone': PLATFORM_XBOX,
    'switch': PLATFORM_SWITCH,
    'Switch': PLATFORM_SWITCH,
    'OnlinePlatform_PS4': PLATFORM_PSN,
    'OnlinePlatform_Unknown': PLATFORM_UNKNOWN,
    'OnlinePlatform_Dingo': PLATFORM_XBOX,
    'OnlinePlatform_Steam': PLATFORM_STEAM,
    'OnlinePlatform_NNX': PLATFORM_SWITCH,

    "{'Value': ['OnlinePlatform', 'OnlinePlatform_Steam']}": PLATFORM_STEAM,
    "{'Value': ['OnlinePlatform', 'OnlinePlatform_Dingo']}": PLATFORM_XBOX,
    "{'Value': ['OnlinePlatform', 'OnlinePlatform_PS4']}": PLATFORM_PSN,
    "{'Value': ['OnlinePlatform', 'OnlinePlatform_Unknown']}": PLATFORM_UNKNOWN,

    # The next values are used for the official API.
    PLATFORM_UNKNOWN: 'unknown',
    str(PLATFORM_UNKNOWN): 'unknown',
    PLATFORM_STEAM: 'steam',
    str(PLATFORM_STEAM): 'steam',
    PLATFORM_PSN: 'ps4',
    str(PLATFORM_PSN): 'ps4',
    PLATFORM_XBOX: 'xboxone',
    str(PLATFORM_XBOX): 'xboxone',
    PLATFORM_SWITCH: 'switch',
    str(PLATFORM_SWITCH): 'switch',

    None: PLATFORM_UNKNOWN,
}


class Season(models.Model):

    title = models.CharField(
        max_length=100,
        unique=True,
    )

    start_date = models.DateTimeField()

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-start_date']


def get_default_season():
    if Season.objects.count() == 0:
        season = Season.objects.create(
            title='Season 1',
            start_date='2015-07-07'  # Game release date
        )

        return season.pk

    return Season.objects.filter(
        start_date__lte=now(),
    )[0].pk


class Map(models.Model):

    title = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    slug = models.CharField(
        max_length=100,
    )

    image = models.FileField(
        upload_to='uploads/files',
        blank=True,
        null=True,
    )

    def __str__(self):
        return self.title or self.slug

    class Meta:
        ordering = ['title']


class Replay(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        db_index=True,
    )

    season = models.ForeignKey(
        Season,
        default=get_default_season,
    )

    title = models.CharField(
        "replay name",
        max_length=128,
        blank=True,
        null=True,
    )

    playlist = models.PositiveIntegerField(
        choices=[(v, k) for k, v in settings.PLAYLISTS.items()],
        default=0,
        blank=True,
        null=True,
    )

    file = models.FileField(
        upload_to='uploads/replay_files',
    )

    heatmap_json_file = models.FileField(
        upload_to='uploads/replay_json_files',
        blank=True,
        null=True,
    )

    location_json_file = models.FileField(
        upload_to='uploads/replay_location_json_files',
        blank=True,
        null=True,
    )

    replay_id = models.CharField(
        "replay ID",
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
    )

    player_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    player_team = models.IntegerField(
        default=0,
        blank=True,
        null=True,
    )

    map = models.ForeignKey(
        Map,
        blank=True,
        null=True,
        db_index=True,
    )

    server_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    timestamp = models.DateTimeField(
        blank=True,
        null=True,
    )

    date_created = models.DateTimeField(
        default=now,
    )

    team_sizes = models.PositiveIntegerField(
        blank=True,
        null=True,
        db_index=True,
    )

    team_0_score = models.IntegerField(
        default=0,
        blank=True,
        null=True,
        db_index=True,
    )

    team_1_score = models.IntegerField(
        default=0,
        blank=True,
        null=True,
        db_index=True,
    )

    match_type = models.CharField(
        max_length=16,
        blank=True,
        null=True,
    )

    privacy = models.PositiveIntegerField(
        'replay privacy',
        choices=[
            (PRIVACY_PRIVATE, 'Private'),
            (PRIVACY_UNLISTED, 'Unlisted'),
            (PRIVACY_PUBLIC, 'Public')
        ],
        default=3,
    )

    # Parser V2 values.
    keyframe_delay = models.FloatField(
        blank=True,
        null=True,
    )

    max_channels = models.IntegerField(
        default=1023,
        blank=True,
        null=True,
    )

    max_replay_size_mb = models.IntegerField(
        "max replay size (MB)",
        default=10,
        blank=True,
        null=True,
    )

    num_frames = models.IntegerField(
        blank=True,
        null=True,
    )

    record_fps = models.FloatField(
        "record FPS",
        default=30.0,
        blank=True,
        null=True,
    )

    shot_data = JSONField(
        blank=True,
        null=True,
    )

    excitement_factor = models.FloatField(
        default=0.00,
    )

    show_leaderboard = models.BooleanField(
        default=False,
    )

    average_rating = models.PositiveIntegerField(
        blank=True,
        null=True,
        default=0,
    )

    crashed_heatmap_parser = models.BooleanField(
        default=False,
    )

    processed = models.BooleanField(
        default=False,
    )

    @cached_property
    def uuid(self):
        return re.sub(r'([A-F0-9]{8})([A-F0-9]{4})([A-F0-9]{4})([A-F0-9]{4})([A-F0-9]{12})', r'\1-\2-\3-\4-\5', self.replay_id).lower()

    def team_x_player_list(self, team):
        return [
            "{}{}".format(
                player.player_name,
                " ({})".format(player.goal_set.count()) if player.goal_set.count() > 0 else '',
            ) for player in self.player_set.filter(
                team=team,
            )
        ]

    def team_x_players(self, team):
        return ', '.join(self.team_x_player_list(team))

    def team_0_players(self):
        return self.team_x_players(0)

    def team_1_players(self):
        return self.team_x_players(1)

    def team_0_player_list(self):
        return self.team_x_player_list(0)

    def team_1_player_list(self):
        return self.team_x_player_list(1)

    def player_pairs(self):
        return zip_longest(self.team_0_player_list(), self.team_1_player_list())

    @cached_property
    def region(self):
        if not self.server_name:
            return 'N/A'

        match = re.search(settings.SERVER_REGEX, self.server_name)

        if match:
            return match.groups()[1]

        return 'N/A'

    def lag_report_url(self):
        base_url = 'https://psyonixhr.wufoo.com/forms/game-server-performance-report'
        if not self.server_name:
            return base_url

        # Split out the server name.
        match = re.search(r'(EU|USE|USW|OCE|SAM)(\d+)(-([A-Z][a-z]+))?', self.server_name).groups()

        return "{}/def/field1={}&field2={}&field13={}".format(
            base_url,
            *match
        )

    @cached_property
    def match_length(self):
        if not self.num_frames or not self.record_fps:
            return 'N/A'

        calculation = self.num_frames / self.record_fps
        minutes, seconds = divmod(calculation, 60)
        return '%d:%02d' % (
            int(minutes),
            int(seconds),
        )

    def calculate_excitement_factor(self):
        # Multiplers for use in factor tweaking.
        swing_rating_multiplier = 8
        goal_count_multiplier = 1.2

        # Calculate how the swing changed throughout the game.
        swing = 0
        swing_values = []

        for goal in self.goal_set.all():
            if goal.player.team == 0:
                swing -= 1
            else:
                swing += 1

            swing_values.append(swing)

        if self.team_0_score > self.team_1_score:
            # Team 0 won, but were they ever losing?
            deficit_values = [x for x in swing_values if x < 0]

            if deficit_values:
                deficit = max(swing_values)
            else:
                deficit = 0

            score_min_def = self.team_0_score - deficit
        else:
            # Team 1 won, but were they ever losing?
            deficit_values = [x for x in swing_values if x < 0]

            if deficit_values:
                deficit = abs(min(deficit_values))
            else:
                deficit = 0

            score_min_def = self.team_1_score - deficit

        if score_min_def != 0:
            swing_rating = float(deficit) / score_min_def * swing_rating_multiplier
        else:
            swing_rating = 0

        # Now we have the swing rating, adjust it by the total number of goals.
        # This gives us a "base value" for each replay and allows replays with
        # lots of goals but not much swing to get reasonable rating. Cap the goal
        # multiplier at 5.
        total_goals = self.team_0_score + self.team_1_score
        if total_goals > 5:
            total_goals = 5

        swing_rating += total_goals * goal_count_multiplier

        return swing_rating

    def calculate_average_rating(self):
        from ..users.models import LeagueRating

        players = self.player_set.exclude(
            online_id__isnull=True,
        )

        num_player_ratings = 0
        total_player_ratings = 0

        for player in players:
            try:
                # Get the latest rating for this player.
                rating = LeagueRating.objects.get(
                    platform=player.platform,
                    online_id=player.online_id,
                    playlist=self.playlist,
                )

                total_player_ratings += rating.tier
                num_player_ratings += 1
            except LeagueRating.DoesNotExist:
                # Should we get the ratings?
                continue

        if num_player_ratings > 0:
            return math.ceil(total_player_ratings / num_player_ratings)
        return 0

    def eligible_for_feature(self, feature):
        features = {
            'playback': settings.PATREON_PLAYBACK_PRICE,
            'boost_analysis': settings.PATREON_BOOST_PRICE,
        }

        patreon_amount = features[feature]

        # Import here to avoid circular imports.
        from ..site.templatetags.site import patreon_pledge_amount

        # Is the uploader a patron?
        if self.user:
            pledge_amount = patreon_pledge_amount({}, user=self.user)

            if pledge_amount >= patreon_amount:
                return True

        # Are any of the players patron?
        players = self.player_set.filter(
            platform__in=['OnlinePlatform_Steam', '1'],
        )

        for player in players:
            pledge_amount = patreon_pledge_amount({}, steam_id=player.online_id)

            if pledge_amount >= patreon_amount:
                return True

        return False

    @property
    def queue_priority(self):
        # Returns one of 'tournament', 'priority', 'general', where 'tournament'
        # is the highest priority.

        # TODO: Add tournament logic.

        if self.eligible_for_playback:
            return 'priority'

        return 'general'

    # Feature eligibility checks.
    @cached_property
    def eligible_for_playback(self):
        return self.eligible_for_feature('playback')

    @cached_property
    def show_playback(self):
        # First of all, is there even a JSON file?
        if not self.location_json_file:
            return False

        return self.eligible_for_feature('playback')

    @cached_property
    def eligible_for_boost_analysis(self):
        return self.eligible_for_feature('boost_analysis')

    @cached_property
    def show_boost_analysis(self):
        # Have we got any boost data yet?
        if self.boostdata_set.count() == 0:
            return False

        return self.eligible_for_feature('boost_analysis')

    # Other stuff
    @cached_property
    def get_human_playlist(self):
        if not self.playlist:
            return 'Unknown'

        display = self.get_playlist_display()
        if display == self.playlist:
            display = 'Unknown'

        return settings.HUMAN_PLAYLISTS.get(self.playlist, display)

    def get_absolute_url(self):
        if self.replay_id:
            return reverse('replay:detail', kwargs={
                'replay_id': re.sub(r'([A-F0-9]{8})([A-F0-9]{4})([A-F0-9]{4})([A-F0-9]{4})([A-F0-9]{12})', r'\1-\2-\3-\4-\5', self.replay_id).lower(),
            })

        return reverse('replay:detail', kwargs={
            'pk': self.pk,
        })

    class Meta:
        ordering = ['-timestamp', '-pk']

    def __str__(self):
        return self.title or str(self.pk) or '[{}] {} {} game on {}. Final score: {}, Uploaded by {}.'.format(
            self.timestamp,
            '{size}v{size}'.format(size=self.team_sizes),
            self.match_type,
            self.map,
            '{}-{}'.format(self.team_0_score, self.team_1_score),
            self.player_name,
        )

    def clean(self):
        if self.pk:
            return

        if self.file:
            # Ensure we're at the start of the file as `clean()` can sometimes
            # be called multiple times (for some reason..)
            self.file.seek(0)

            file_url = self.file.url  # To help the exception handler

            try:
                replay = Pyrope(self.file.read())
            except bitstring.ReadError:
                raise ValidationError("The file you selected does not seem to be a valid replay file.")

            # Check if this replay has already been uploaded.
            replays = Replay.objects.filter(
                replay_id=replay.header['Id'],
            )

            if replays.count() > 0:
                raise ValidationError(mark_safe("This replay has already been uploaded, <a target='_blank' href='{}'>you can view it here</a>.".format(
                    replays[0].get_absolute_url()
                )))

            self.replay_id = replay.header['Id']

    def save(self, *args, **kwargs):
        parse_netstream = False

        if 'parse_netstream' in kwargs:
            parse_netstream = kwargs.pop('parse_netstream')

        super(Replay, self).save(*args, **kwargs)

        if self.file and not self.processed:
            try:
                if parse_netstream:
                    # Header parse?
                    parse_replay_netstream(self.pk)
                else:
                    parse_replay_header(self.pk)
            except:
                logger.exception('Replay save failed')


class Player(models.Model):

    replay = models.ForeignKey(
        Replay,
    )

    player_name = models.CharField(
        max_length=100,
        db_index=True,
    )

    team = models.IntegerField()

    # 1.06 data
    score = models.PositiveIntegerField(
        default=0,
        blank=True,
    )

    goals = models.PositiveIntegerField(
        default=0,
        blank=True,
    )

    shots = models.PositiveIntegerField(
        default=0,
        blank=True,
    )

    assists = models.PositiveIntegerField(
        default=0,
        blank=True,
    )

    saves = models.PositiveIntegerField(
        default=0,
        blank=True,
    )

    platform = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
    )

    online_id = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        db_index=True,
    )

    bot = models.BooleanField(
        default=False,
    )

    spectator = models.BooleanField(
        default=False,
    )

    heatmap = models.FileField(
        upload_to='uploads/heatmap_files',
        blank=True,
        null=True,
    )

    user_entered = models.BooleanField(
        default=False,
    )

    # Taken from the netstream.
    actor_id = models.PositiveIntegerField(
        default=0,
        blank=True,
        null=True,
    )

    unique_id = models.CharField(
        max_length=128,
        blank=True,
        null=True,
    )

    party_leader = models.ForeignKey(
        'self',
        blank=True,
        null=True,
    )

    camera_settings = JSONField(
        blank=True,
        null=True,
    )

    vehicle_loadout = JSONField(
        blank=True,
        null=True,
    )

    total_xp = models.IntegerField(
        default=0,
        blank=True,
        null=True,
    )

    # Other stuff.
    boost_data = JSONField(
        blank=True,
        null=True,
    )

    @cached_property
    def get_rating_data(self):
        from ..users.models import LeagueRating
        from ..users.templatetags.ratings import tier_name

        if self.replay.playlist not in settings.RANKED_PLAYLISTS:
            return

        try:
            rating = LeagueRating.objects.get_or_request(
                platform=self.platform,
                online_id=self.online_id if PLATFORMS_MAPPINGS[self.platform] == PLATFORM_STEAM else self.player_name,
                playlist=self.replay.playlist,
            )

            if not rating:
                return {
                    'image': static('img/tiers/icons/0.png'),
                    'tier_name': tier_name(0)
                }

            return {
                'image': static('img/tiers/icons/{}.png'.format(rating.tier)),
                'tier_name': tier_name(rating.tier)
            }
        except LeagueRating.DoesNotExist:
            pass

        return {
            'image': static('img/tiers/icons/0.png'),
            'tier_name': 'Unranked'
        }

    @cached_property
    def vehicle_data(self):
        """
        {
            "RocketTrail": {"Name": "Boost_HolyLight", "Id": 44},
            "Topper": {"Name": "Hat_Tiara", "Id": 495},
            "Version": 12,
            "Wheels": {"Name": "WHEEL_Atlantis", "Id": 359},
            "Body": {"Name": "Body_Force", "Id": 22},
            "Antenna": {"Name": null, "Id": 0},
            "Decal": {"Name": "Skin_Force_Junk", "Id": 1178},
            "Unknown2": 0,
            "Unknown1": 0
        }
        """

        components = {}

        if not self.vehicle_loadout:
            return components

        if type(self.vehicle_loadout) == list:
            """
            [
              403,  # Body
              0,    # Decal. 330 = Flames
              376,  # Wheels. 386 = Christiano, 376 = OEM
              63,   # Rocket Trail. 578 = Candy Corn
              0,    # Antenna. 1 = 8-Ball
              0,    # Topper. 796 = Deadmau5
              0     #
            ],
            """

            if len(self.vehicle_loadout) == 9:
                self.vehicle_loadout = self.vehicle_loadout[1:-1]

            assert len(self.vehicle_loadout) == 7

            component_maps = [
                'body',
                'decal',
                'wheels',
                'trail',
                'antenna',
                'topper',
            ]

            for index, component in enumerate(self.vehicle_loadout):
                if component > 0:
                    get_component = Component.objects.filter(
                        type=component_maps[index],
                        internal_id=component,
                    )

                    if get_component.exists():
                        components[component_maps[index]] = get_component[0]
                    else:
                        components[component_maps[index]] = Component.objects.create(
                            type=component_maps[index],
                            internal_id=component,
                            name='Unknown',
                        )

        elif type(self.vehicle_loadout) == dict:
            component_maps = {
                'Body': {'type': 'body', 'replace': 'Body_'},
                'Decal': {'type': 'decal', 'replace': 'Skin_'},
                'Wheels': {'type': 'wheels', 'replace': 'WHEEL_'},
                'RocketTrail': {'type': 'trail', 'replace': 'Boost_'},
                'Antenna': {'type': 'antenna', 'replace': 'Antenna '},
                'Topper': {'type': 'topper', 'replace': 'Hat_'},
            }

            for component_type, mappings in component_maps.items():
                if component_type in self.vehicle_loadout and self.vehicle_loadout[component_type]['Name']:
                    try:
                        components[mappings['type']] = Component.objects.get_or_create(
                            type=mappings['type'],
                            internal_id=self.vehicle_loadout[component_type]['Id'],
                            defaults={
                                'name': self.vehicle_loadout[component_type]['Name'].replace(mappings['replace'], '').replace('_', ' ')
                            }
                        )[0]

                        if components[mappings['type']].name == 'Unknown':
                            components[mappings['type']].name = self.vehicle_loadout[component_type]['Name'].replace(mappings['replace'], '').replace('_', ' ')
                            components[mappings['type']].save()
                    except Exception:
                        pass

        return components

    def get_absolute_url(self):
        if self.bot or self.platform == '0' or not self.platform:
            return '#1'

        try:
            return reverse('users:player', kwargs={
                'platform': PLATFORMS_MAPPINGS[self.platform],
                'player_id': self.online_id if int(self.platform) == PLATFORM_STEAM else self.player_name,
            })
        except Exception:
            return '#2'

    def __str__(self):
        return '{} on Team {}'.format(
            self.player_name,
            self.team,
        )

    class Meta:
        ordering = ('team', '-score', 'player_name')


class Goal(models.Model):

    replay = models.ForeignKey(
        Replay,
        db_index=True,
    )

    # Goal 1, 2, 3 etc..
    number = models.PositiveIntegerField()

    player = models.ForeignKey(
        Player,
        db_index=True,
    )

    frame = models.IntegerField(
        blank=True,
        null=True,
    )

    @cached_property
    def goal_time(self):
        if not self.frame or not self.replay.record_fps:
            return 'N/A'

        calculation = self.frame / self.replay.record_fps
        minutes, seconds = divmod(calculation, 60)
        return '%d:%02d' % (
            int(minutes),
            int(seconds),
        )

    def __str__(self):
        try:
            return 'Goal {} by {}'.format(
                self.number,
                self.player,
            )
        except Player.DoesNotExist:
            return 'Goal {}'.format(
                self.number,
            )

    class Meta:
        ordering = ['frame']


class ReplayPack(models.Model):

    title = models.CharField(
        max_length=50,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_index=True,
    )

    replays = models.ManyToManyField(
        Replay,
        blank=True,
    )

    file = models.FileField(
        upload_to='uploads/replaypack_files',
        blank=True,
        null=True,
    )

    date_created = models.DateTimeField(
        auto_now_add=True,
    )

    last_updated = models.DateTimeField(
        auto_now=True,
    )

    @cached_property
    def maps(self):
        maps = Map.objects.filter(
            id__in=set(self.replays.values_list('map_id', flat=True))
        ).values_list('title', flat=True)

        return ', '.join(maps)

    @cached_property
    def goals(self):
        if not self.replays.count():
            return 0
        return self.replays.aggregate(
            num_goals=models.Sum(models.F('team_0_score') + models.F('team_1_score'))
        )['num_goals']

    @cached_property
    def players(self):
        return set(Player.objects.filter(
            replay_id__in=self.replays.values_list('id', flat=True),
        ).values_list('player_name', flat=True))

    @cached_property
    def total_duration(self):
        calculation = 0

        if self.replays.count():
            calculation = self.replays.aggregate(models.Sum('num_frames'))['num_frames__sum'] / 30

        minutes, seconds = divmod(calculation, 60)
        hours, minutes = divmod(minutes, 60)

        return '{} {}m {}s'.format(
            '{}h'.format(int(hours)) if hours > 0 else '',
            int(minutes),
            int(seconds),
        )

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('replaypack:detail', kwargs={
            'pk': self.pk,
        })

    class Meta:
        ordering = ['-last_updated', '-date_created']


class BoostData(models.Model):

    replay = models.ForeignKey(
        Replay,
        db_index=True,
    )

    player = models.ForeignKey(
        Player,
    )

    frame = models.PositiveIntegerField()

    value = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(255)]
    )

    class Meta:
        ordering = ['player', 'frame']
        # unique_together = [('player', 'frame', 'value')]


class Component(models.Model):

    type = models.CharField(
        max_length=8,
        choices=[
            ('trail', 'Trail'),
            ('antenna', 'Antenna'),
            ('wheels', 'Wheels'),
            ('decal', 'Decal'),
            ('body', 'Body'),
            ('topper', 'Topper')
        ],
        default='body',
    )

    internal_id = models.PositiveIntegerField()

    name = models.CharField(
        max_length=100,
        default='Unknown',
    )
