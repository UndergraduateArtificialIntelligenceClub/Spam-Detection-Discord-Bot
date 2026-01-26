import discord
from discord.ext import commands
from datetime import datetime
from typing import Optional, Dict
import pytz

from utils.scam_detector import ScamDetector
from utils.logger import setup_logger
from utils.dataset_logger import DatasetLogger
from utils.stats_tracker import StatsTracker
from config import Config

# Initialize logger
logger = setup_logger(__name__)

# Set timezone to Edmonton
LOCAL_TZ = pytz.timezone('America/Edmonton')


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scam_detector = ScamDetector()
        self.dataset_logger = DatasetLogger()
        self.stats_tracker = StatsTracker()
        self.whitelisted_roles = ['Admin', 'Moderator', 'executive', 'chat revive ping', 'camouflage', 'Advisor', '👑', 'stats nerd', 'assembly GOD', 'regex GOD', 'the negotiator', 'AutoRecruiter', 'Sponsor', 'Industry Associate', 'Project Leads', 'AI Due Diligence Team', 'Palm Pilot 2.0 Team', 'RAG Bot Team', 'Alzheimer AI Team', 'Crypto Forecast Team', 'Clubmate AI Team', '2425 Executives', 'Crossy Road Bot Team', 'Industrial Safety Bot Team', 'Past UAIS Project Team', 'VeriRAG Team']
        
        # Store log messages for false alarm handling
        # Format: {log_message_id: {'content': str, 'user': discord.User, 'channel': discord.Channel}}
        self.flagged_messages: Dict[int, dict] = {}
        
    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f'Moderation cog loaded. Monitoring messages...')
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Monitor all messages for scam content."""
        
        logger.info(f"[DEBUG] Received message from {message.author.name}: {message.content[:80]}")
        
        # Ignore bot messages
        if message.author.bot:
            logger.info("[DEBUG] Ignoring bot message")
            return
        
        # Ignore commands
        if message.content.startswith(self.bot.command_prefix):
            logger.info("[DEBUG] Ignoring command")
            return
        
        # Check if user has whitelisted role
        if isinstance(message.author, discord.Member):
            user_roles = [role.name for role in message.author.roles]
            logger.info(f"[DEBUG] User roles: {user_roles}")
            if any(role in self.whitelisted_roles for role in user_roles):
                logger.info("[DEBUG] User has whitelisted role, skipping")
                return
        
        # Increment messages analyzed counter
        self.stats_tracker.increment_analyzed()
        
        try:
            logger.info(f"[DEBUG] Analyzing message: {message.content[:100]}")
            # Detect scam
            is_scam, confidence, reason = self.scam_detector.detect(message.content)
            logger.info(f"[DEBUG] Detection result: is_scam={is_scam}, confidence={confidence:.2%}, reason={reason}")
            
            if is_scam:
                logger.warning(f"[SCAM DETECTED] Processing message from {message.author.name}")
                self.stats_tracker.increment_flagged()
                await self._handle_scam_message(message, confidence, reason)
            else:
                logger.info("[DEBUG] Message is clean")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Handle reactions on log messages for false alarm reporting."""
        
        # Ignore bot reactions
        if user.bot:
            return
        
        # Check if this is a false alarm reaction (❌) on a log message
        if str(reaction.emoji) == "❌" and reaction.message.id in self.flagged_messages:
            # Check if user has moderator permissions
            if not isinstance(user, discord.Member):
                return
            
            if not user.guild_permissions.manage_messages:
                await user.send("❌ You need 'Manage Messages' permission to report false alarms.")
                return
            
            # Handle false alarm
            await self._handle_false_alarm(reaction.message, user)
    
    async def _handle_scam_message(
        self, 
        message: discord.Message, 
        confidence: float, 
        reason: str
    ):
        """Handle detected scam message."""
        
        member = message.author
        guild = message.guild
        original_channel = message.channel
        original_content = message.content
        
        # Store original message time in Edmonton timezone
        message_sent_time = message.created_at.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        
        logger.warning(
            f"Scam detected from {member.name}#{member.discriminator} "
            f"({member.id}) with confidence {confidence:.2%} at {message_sent_time}"
        )
        
        # Get join date
        joined_at = "Unknown"
        if isinstance(member, discord.Member) and member.joined_at:
            joined_at = member.joined_at.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        
        # Log to CSV dataset BEFORE deleting (in case deletion fails)
        logger.info("[DATASET] Logging flagged message to CSV dataset")
        self.dataset_logger.log_flagged_message(message, confidence, reason, joined_at)
        
        # Delete the message
        try:
            await message.delete()
            logger.info(f"Deleted scam message from {member.name}")
        except discord.errors.Forbidden:
            logger.error("Bot lacks permission to delete messages")
            return
        except Exception as e:
            logger.error(f"Error deleting message: {e}")
            return
        
        # Send DM notification to the user
        await self._send_user_notification(member, guild)
        
        # Send log to private channel and store for false alarm handling
        log_message_id = await self._send_log(message, member, joined_at, confidence, reason, message_sent_time)
        
        # Store message data for potential restoration
        if log_message_id:
            self.flagged_messages[log_message_id] = {
                'content': original_content,
                'user': member,
                'channel': original_channel,
                'confidence': confidence,
                'reason': reason
            }
    
    async def _handle_false_alarm(self, log_message: discord.Message, moderator: discord.Member):
        """Handle false alarm report - restore message and update stats."""
        
        try:
            message_data = self.flagged_messages.get(log_message.id)
            if not message_data:
                await moderator.send("❌ Could not find original message data.")
                return
            
            original_user = message_data['user']
            original_channel = message_data['channel']
            original_content = message_data['content']
            
            # Increment false alarm counter
            self.stats_tracker.increment_false_alarm()
            
            # Create restoration embed
            restore_embed = discord.Embed(
                title="⚠️ False Alarm - Message Restored",
                description=(
                    f"A message from {original_user.mention} was incorrectly flagged and has been restored.\n"
                    f"**Reported by:** {moderator.mention}"
                ),
                color=discord.Color.orange(),
                timestamp=datetime.now(LOCAL_TZ)
            )
            
            restore_embed.add_field(
                name="Original User",
                value=f"{original_user.mention} ({original_user.name}#{original_user.discriminator})",
                inline=False
            )
            
            restore_embed.add_field(
                name="Message Content",
                value=original_content[:1024] if original_content else "*No content*",
                inline=False
            )
            
            restore_embed.set_footer(text=f"False alarm reported by {moderator.name}")
            
            # Send restored message to original channel
            try:
                await original_channel.send(embed=restore_embed)
                logger.info(f"[FALSE ALARM] Restored message to {original_channel.name}")
            except discord.errors.Forbidden:
                logger.error(f"[FALSE ALARM] Cannot send to {original_channel.name} - missing permissions")
            
            # Update the log message to show it was a false alarm
            updated_embed = log_message.embeds[0]
            updated_embed.color = discord.Color.orange()
            updated_embed.title = "⚠️ FALSE ALARM - Message Restored"
            updated_embed.set_footer(text=f"False alarm reported by {moderator.name} | Message restored to channel")
            
            await log_message.edit(embed=updated_embed)
            await log_message.clear_reactions()
            
            # Send confirmation to log channel (not DM)
            confirmation_embed = discord.Embed(
                title="✅ False Alarm Processed",
                description=(
                    f"**Reported by:** {moderator.mention}\n"
                    f"**Original User:** {original_user.mention}\n"
                    f"**Message restored to:** {original_channel.mention}\n"
                    f"**Total False Alarms:** {self.stats_tracker.overall_stats['total_false_alarms']}"
                ),
                color=discord.Color.green(),
                timestamp=datetime.now(LOCAL_TZ)
            )
            
            await log_message.channel.send(embed=confirmation_embed)
            
            # Remove from tracking
            del self.flagged_messages[log_message.id]
            
            logger.info(f"[FALSE ALARM] Processed by {moderator.name} for message from {original_user.name}")
            
        except Exception as e:
            logger.error(f"[FALSE ALARM] Error handling false alarm: {e}", exc_info=True)
            await moderator.send(f"❌ Error processing false alarm: {e}")
    
    async def _send_user_notification(self, member: discord.Member, guild: discord.Guild):
        """Send a DM notification to the user whose message was flagged."""
        
        try:
            embed = discord.Embed(
                title="⚠️ Message Flagged",
                description=(
                    f"Your recent message in **{guild.name}** has been flagged by our automated "
                    "moderation system and removed."
                ),
                color=discord.Color.orange()
            )
            
            embed.add_field(
                name="What does this mean?",
                value=(
                    "Our system detected content that may violate server rules. "
                    "If you believe this was a mistake, please don't worry!"
                ),
                inline=False
            )
            
            embed.add_field(
                name="Was this a false alarm?",
                value=(
                    "Please contact the server moderators. "
                    "Your message has been logged, and if this was an error, "
                    "moderators can restore it immediately."
                ),
                inline=False
            )
            
            embed.set_footer(text="Automated Security System")
            
            await member.send(embed=embed)
            logger.info(f"Successfully sent DM notification to {member.name}")
            
        except discord.errors.Forbidden:
            logger.warning(
                f"Could not send DM to {member.name} (DMs disabled or bot blocked)"
            )
        except Exception as e:
            logger.error(f"Error sending DM notification to {member.name}: {e}", exc_info=True)
    
    async def _send_log(
        self,
        message: discord.Message,
        member: discord.Member,
        joined_at: str,
        confidence: float,
        reason: str,
        message_sent_time: str
    ) -> Optional[int]:
        """Send log to the private logging channel. Returns log message ID."""
        
        log_channel = self.bot.get_channel(Config.LOG_CHANNEL_ID)
        
        if not log_channel:
            logger.error(f"Log channel {Config.LOG_CHANNEL_ID} not found")
            return None
        
        try:
            detected_at = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
            
            embed = discord.Embed(
                title="🚨 Scam Message Deleted",
                description="React with ❌ to mark as false alarm and restore message",
                color=discord.Color.red(),
                timestamp=datetime.now(LOCAL_TZ)
            )
            
            embed.add_field(
                name="User",
                value=f"{member.mention} ({member.name}#{member.discriminator})",
                inline=False
            )
            embed.add_field(name="User ID", value=str(member.id), inline=True)
            embed.add_field(name="Joined Server", value=joined_at, inline=True)
            embed.add_field(name="Detection Method", value=reason, inline=False)
            embed.add_field(name="Confidence", value=f"{confidence:.2%}", inline=True)
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            
            embed.add_field(name="Message Sent", value=message_sent_time, inline=True)
            embed.add_field(name="Detected At", value=detected_at, inline=True)
            
            embed.add_field(
                name="Message Content",
                value=message.content[:1024] if message.content else "*No content*",
                inline=False
            )
            
            if member.avatar:
                embed.set_thumbnail(url=member.avatar.url)
            
            embed.set_footer(text="User notified via DM | Logged to training dataset")
            
            mod_role = message.guild.get_role(Config.MODERATOR_ROLE_ID)
            
            if mod_role:
                content = f"{mod_role.mention} Spam detected!"
            else:
                logger.warning(f"Moderator role {Config.MODERATOR_ROLE_ID} not found")
                content = "Spam detected!"
            
            log_message = await log_channel.send(content=content, embed=embed)
            
            # Add reaction for false alarm reporting
            await log_message.add_reaction("❌")
            
            logger.info(f"Sent log to channel {log_channel.name}")
            
            return log_message.id
            
        except Exception as e:
            logger.error(f"Error sending log: {e}", exc_info=True)
            return None
    
    @commands.command(name='check')
    @commands.has_permissions(administrator=True)
    async def check_message(self, ctx: commands.Context, *, text: str):
        """Manually check if a message is a scam (Admin only)."""
        
        is_scam, confidence, reason = self.scam_detector.detect(text)
        
        embed = discord.Embed(
            title="Scam Detection Result",
            color=discord.Color.red() if is_scam else discord.Color.green()
        )
        
        embed.add_field(name="Is Scam?", value="Yes" if is_scam else "No", inline=True)
        embed.add_field(name="Confidence", value=f"{confidence:.2%}", inline=True)
        embed.add_field(name="Reason", value=reason or "N/A", inline=False)
        embed.add_field(name="Tested Message", value=text[:1024], inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='stats')
    @commands.has_permissions(administrator=True)
    async def show_stats(self, ctx: commands.Context):
        """Show comprehensive bot statistics (Admin only)."""
        
        stats = self.stats_tracker.get_comprehensive_stats()
        
        embed = discord.Embed(
            title="📊 Bot Statistics Dashboard",
            color=discord.Color.blue(),
            timestamp=datetime.now(LOCAL_TZ)
        )
        
        # Session Stats
        embed.add_field(
            name="📍 Current Session",
            value=(
                f"**Uptime:** {stats['session_uptime']}\n"
                f"**Analyzed:** {stats['session_messages_analyzed']:,}\n"
                f"**Flagged:** {stats['session_messages_flagged']:,}\n"
                f"**Detection Rate:** {stats['session_detection_rate']:.2f}%\n"
                f"**Msg/Hour:** {stats['session_messages_per_hour']:.1f}"
            ),
            inline=True
        )
        
        # Overall Stats
        embed.add_field(
            name="📊 Overall Statistics",
            value=(
                f"**Total Uptime:** {stats['total_uptime']}\n"
                f"**Total Analyzed:** {stats['total_messages_analyzed']:,}\n"
                f"**Total Flagged:** {stats['total_messages_flagged']:,}\n"
                f"**Detection Rate:** {stats['total_detection_rate']:.2f}%"
            ),
            inline=True
        )
        
        # Accuracy Metrics
        embed.add_field(
            name="🎯 Accuracy",
            value=(
                f"**False Alarms:** {stats['total_false_alarms']}\n"
                f"**Accuracy:** {stats['overall_accuracy']:.1f}%\n"
                f"**True Positives:** {stats['total_messages_flagged'] - stats['total_false_alarms']}"
            ),
            inline=True
        )
        
        # Dataset Info
        embed.add_field(
            name="💾 Training Dataset",
            value=(
                f"**Samples:** {stats['dataset_total']:,}\n"
                f"**Size:** {stats['dataset_size_mb']:.2f} MB\n"
                f"**Format:** CSV (UTF-8)"
            ),
            inline=True
        )
        
        # Detection Methods
        if stats['detection_methods']:
            methods_text = "\n".join([
                f"**{method}:** {count}" 
                for method, count in stats['detection_methods'].items()
            ])
            embed.add_field(
                name="🔍 Detection Methods",
                value=methods_text,
                inline=True
            )
        
        # System Resources
        if stats['system']:
            sys = stats['system']
            embed.add_field(
                name="💻 Bot Resources",
                value=(
                    f"**CPU:** {sys.get('process_cpu_percent', 0):.1f}%\n"
                    f"**RAM:** {sys.get('process_memory_mb', 0):.1f} MB"
                ),
                inline=True
            )
        
        # Bot Config
        embed.add_field(
            name="⚙️ Configuration",
            value=(
                f"**Servers:** {len(self.bot.guilds)}\n"
                f"**Threshold:** {Config.SCAM_THRESHOLD:.0%}"
            ),
            inline=True
        )
        
        embed.set_footer(text="React ❌ on log messages to report false alarms")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='dataset_info')
    @commands.has_permissions(administrator=True)
    async def dataset_info(self, ctx: commands.Context):
        """Show detailed information about the training dataset (Admin only)."""
        
        stats = DatasetLogger.get_dataset_stats()
        
        if not stats['exists']:
            await ctx.send("❌ No dataset file found yet. Start flagging messages to build the dataset!")
            return
        
        embed = discord.Embed(
            title="📊 Training Dataset Information",
            description=f"Dataset location: `{stats['file_path']}`",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Total Samples", value=str(stats['total_messages']), inline=True)
        embed.add_field(name="File Size", value=f"{stats['file_size']:,} bytes ({stats['file_size']/1024/1024:.2f} MB)", inline=True)
        embed.add_field(name="Format", value="CSV (UTF-8)", inline=True)
        
        methods = stats.get('detection_methods', {})
        if methods:
            method_breakdown = "\n".join([f"• {method}: {count}" for method, count in methods.items()])
            embed.add_field(name="Detection Methods", value=method_breakdown, inline=False)
        
        embed.set_footer(text="Use this dataset to fine-tune your spam detection model")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='clear_stats')
    @commands.has_permissions(administrator=True)
    async def clear_stats(self, ctx: commands.Context, scope: str = None):
        """
        Clear bot statistics (Admin only).
        
        Usage:
            !clear_stats session  - Clear only current session stats
            !clear_stats overall  - Clear overall/persistent stats
            !clear_stats all      - Clear everything (session + overall)
        
        Note: CSV dataset is NEVER affected by this command.
        """
        
        if not scope or scope.lower() not in ['session', 'overall', 'all']:
            embed = discord.Embed(
                title="❌ Invalid Usage",
                description=(
                    "Please specify what to clear:\n"
                    "`!clear_stats session` - Clear current session only\n"
                    "`!clear_stats overall` - Clear overall stats only\n"
                    "`!clear_stats all` - Clear both session and overall\n\n"
                    "**Note:** The CSV training dataset is never affected."
                ),
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        scope = scope.lower()
        
        # Create confirmation message
        confirm_embed = discord.Embed(
            title="⚠️ Confirm Stats Clear",
            color=discord.Color.orange()
        )
        
        if scope == 'session':
            confirm_embed.description = (
                "This will reset **current session** statistics:\n"
                "• Session messages analyzed\n"
                "• Session messages flagged\n"
                "• Session uptime\n\n"
                "**Overall stats and CSV dataset will NOT be affected.**"
            )
        elif scope == 'overall':
            confirm_embed.description = (
                "This will reset **overall/persistent** statistics:\n"
                "• Total messages analyzed (all-time)\n"
                "• Total messages flagged (all-time)\n"
                "• Total false alarms (all-time)\n"
                "• Accuracy metrics\n\n"
                "**Session stats and CSV dataset will NOT be affected.**"
            )
        else:  # all
            confirm_embed.description = (
                "This will reset **ALL** statistics:\n"
                "• Session stats\n"
                "• Overall/persistent stats\n"
                "• All counters will be reset to 0\n\n"
                "**⚠️ WARNING: CSV dataset will NOT be affected.**\n"
                "This only clears counters, not your training data."
            )
        
        confirm_embed.add_field(
            name="To Confirm",
            value="React with ✅ to proceed or ❌ to cancel",
            inline=False
        )
        
        confirm_msg = await ctx.send(embed=confirm_embed)
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            
            if str(reaction.emoji) == "✅":
                # Perform the clear operation
                if scope == 'session':
                    self.stats_tracker.session_start_time = datetime.now(LOCAL_TZ)
                    self.stats_tracker.session_messages_analyzed = 0
                    self.stats_tracker.session_messages_flagged = 0
                    
                    result_embed = discord.Embed(
                        title="✅ Session Stats Cleared",
                        description="Current session statistics have been reset.",
                        color=discord.Color.green()
                    )
                    
                elif scope == 'overall':
                    self.stats_tracker.overall_stats = {
                        'total_messages_analyzed': 0,
                        'total_messages_flagged': 0,
                        'total_false_alarms': 0,
                        'first_started': datetime.now(LOCAL_TZ).isoformat(),
                        'last_updated': datetime.now(LOCAL_TZ).isoformat()
                    }
                    self.stats_tracker._save_overall_stats()
                    
                    result_embed = discord.Embed(
                        title="✅ Overall Stats Cleared",
                        description="Overall/persistent statistics have been reset.",
                        color=discord.Color.green()
                    )
                    
                else:  # all
                    # Clear session
                    self.stats_tracker.session_start_time = datetime.now(LOCAL_TZ)
                    self.stats_tracker.session_messages_analyzed = 0
                    self.stats_tracker.session_messages_flagged = 0
                    
                    # Clear overall
                    self.stats_tracker.overall_stats = {
                        'total_messages_analyzed': 0,
                        'total_messages_flagged': 0,
                        'total_false_alarms': 0,
                        'first_started': datetime.now(LOCAL_TZ).isoformat(),
                        'last_updated': datetime.now(LOCAL_TZ).isoformat()
                    }
                    self.stats_tracker._save_overall_stats()
                    
                    result_embed = discord.Embed(
                        title="✅ All Stats Cleared",
                        description="All statistics (session + overall) have been reset.",
                        color=discord.Color.green()
                    )
                
                result_embed.add_field(
                    name="📁 CSV Dataset Status",
                    value="✅ Training dataset remains untouched and safe",
                    inline=False
                )
                
                await ctx.send(embed=result_embed)
                logger.info(f"[STATS] {scope.upper()} stats cleared by {ctx.author.name}")
                
            else:
                await ctx.send("❌ Stats clear cancelled. No changes made.")
                
        except Exception as e:
            await ctx.send(f"⏱️ Stats clear timed out or error occurred: {e}")
    
    @commands.command(name='help', aliases=['commands', 'cmds', 'bothelp'])
    async def show_help(self, ctx: commands.Context, category: str = None):
        """
        Show available bot commands organized by permission level.
        
        Usage:
            !help              - Show all commands
            !help admin        - Show admin-only commands
            !help mod          - Show moderator commands
            !help all          - Show all commands (same as no argument)
            
        Aliases: !commands, !cmds, !bothelp
        """
        
        embed = discord.Embed(
            title="🤖 Bot Command Reference",
            color=discord.Color.blue(),
            timestamp=datetime.now(LOCAL_TZ)
        )
        
        # Determine what to show
        show_all = not category or category.lower() in ['all', 'help']
        show_admin = show_all or category.lower() == 'admin'
        show_mod = show_all or category.lower() in ['mod', 'moderator']
        
        # Admin Commands
        if show_admin:
            admin_commands = (
                "**`!check <text>`**\n"
                "Manually test if text would be flagged as spam\n\n"
                
                "**`!stats`**\n"
                "View comprehensive bot statistics (session + overall)\n\n"
                
                "**`!dataset_info`**\n"
                "View training dataset details and size\n\n"
                
                "**`!clear_stats <session|overall|all>`**\n"
                "Clear statistics (CSV dataset never affected)\n"
                "• `session` - Current session only\n"
                "• `overall` - Persistent stats only\n"
                "• `all` - Everything\n\n"
                
                "**`!help [category]`**\n"
                "Show this help message\n"
                "Categories: `admin`, `mod`, `all`"
            )
            
            embed.add_field(
                name="👑 Administrator Commands",
                value=admin_commands,
                inline=False
            )
        
        # Moderator Commands
        if show_mod:
            mod_commands = (
                "**React with ❌ on log messages**\n"
                "Mark a flagged message as false alarm\n"
                "• Automatically restores the message\n"
                "• Updates accuracy statistics\n"
                "• Posts confirmation in log channel\n\n"
                
                "**Note:** Requires `Manage Messages` permission"
            )
            
            embed.add_field(
                name="🛡️ Moderator Actions",
                value=mod_commands,
                inline=False
            )
        
        # Whitelisted Roles Info
        if show_all:
            whitelist_info = (
                f"Users with these roles bypass spam detection:\n"
                f"• {', '.join(self.whitelisted_roles)}\n\n"
                "These roles are set in the bot configuration."
            )
            
            embed.add_field(
                name="⚪ Whitelisted Roles",
                value=whitelist_info,
                inline=False
            )
        
        # Detection Info
        if show_all:
            detection_info = (
                "**Methods:**\n"
                "• ML Model Detection (BERT-based)\n"
                "• Pattern Matching (Discord-specific scams)\n\n"
                
                "**What happens when spam is detected:**\n"
                "1. Message is deleted immediately\n"
                "2. User receives a DM notification\n"
                "3. Log posted to moderator channel\n"
                "4. Message saved to training dataset\n"
                "5. Statistics updated"
            )
            
            embed.add_field(
                name="🔍 Spam Detection",
                value=detection_info,
                inline=False
            )
        
        # Footer with tips
        embed.set_footer(
            text="Tip: React ❌ on any log message to mark as false alarm | Bot monitors all non-whitelisted messages"
        )
        
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))